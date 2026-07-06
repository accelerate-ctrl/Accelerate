"""w2app HTTP server.

Routes:
  POST /api/runs                    multipart: brd + sdd_1 (+ sdd_2, zenagent_is) -> run
  GET  /api/runs                    run list
  GET  /api/runs/{id}               state (escrow-free), incl. D.5 panel when waiting
  POST /api/runs/{id}/approve       D.5 operator approval (body: {approve: bool, reason})
  GET  /api/runs/{id}/download/{k}  whitelisted artifacts only
  GET  /api/packets/next?runner_id  claim the next open packet across runs
  POST /api/packets/{run}/{pid}/result   runner posts {result, usage}
  GET  /                            operator console (static)

The server never calls a model. Billing safety lives in the runner
(runner/billing_guard.py); server-side the invariant is architectural: there is
no Anthropic client here to bill anything.
"""
from __future__ import annotations
import json
import shutil
import time
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import os

from fastapi import Request
from fastapi.responses import Response

from . import orchestrator, packets, packet_shapes
from .storage import (new_run_id, run_dir, save_state, load_state, list_runs,
                      public_state, resolve_download)
from .config import RUNS_DIR, DATA_DIR, EVAL_PROTOCOL

app = FastAPI(title="Zennify W2 Evaluation Bench", version="2.0")

W2APP_TOKEN = os.environ.get("W2APP_TOKEN", "")


def _parse_member_tokens() -> dict:
    """TR-29 member registry: W2APP_TOKENS="alice:tokA,bob:tokB" maps each
    member to a personal token (owner-pays runner affinity, PRD FR-13).
    The single-token W2APP_TOKEN is still honoured as member "operator".
    Empty registry = open local/dev mode (unchanged v1.1 behavior)."""
    out = {}
    for pair in os.environ.get("W2APP_TOKENS", "").split(","):
        pair = pair.strip()
        if ":" in pair:
            member, tok = pair.split(":", 1)
            if member.strip() and tok.strip():
                out[tok.strip()] = member.strip()
    if W2APP_TOKEN:
        out.setdefault(W2APP_TOKEN, "operator")
    return out


MEMBER_BY_TOKEN = _parse_member_tokens()

# ---- runner heartbeat ledger (TR-29): in-memory, persisted with a throttle —
# a GCS-FUSE write per 3-second poll per member is pointless Class-A churn.
RUNNERS: dict = {}
_RUNNERS_FILE = DATA_DIR / "runners.json"
_RUNNERS_PERSIST_EVERY = 30.0
_runners_persisted_at = 0.0
if _RUNNERS_FILE.exists():
    try:
        RUNNERS.update(json.loads(_RUNNERS_FILE.read_text()))
    except Exception:
        pass


def _heartbeat(member: str | None, runner_id: str, engine: str | None) -> None:
    global _runners_persisted_at
    key = member or "operator"
    RUNNERS[key] = {"member": key, "runner_id": runner_id,
                    "engine": engine or "",
                    "last_seen": time.strftime("%Y-%m-%dT%H:%M:%S")}
    now = time.time()
    if now - _runners_persisted_at >= _RUNNERS_PERSIST_EVERY:
        _runners_persisted_at = now
        try:
            _RUNNERS_FILE.write_text(json.dumps(RUNNERS, indent=2))
        except Exception:
            pass  # heartbeat persistence is best-effort; memory copy stands


def _member_of(request: Request) -> str | None:
    supplied = (request.headers.get("x-w2-token")
                or request.query_params.get("token", ""))
    return MEMBER_BY_TOKEN.get(supplied)


@app.middleware("http")
async def token_auth(request: Request, call_next):
    """Member-token auth on /api/* (TR-29). Every presenting token resolves to
    a member id (stashed on request.state); 401 otherwise. Static surfaces
    (landing, console) stay exempt — the console prompts for the token on its
    first API call. When no tokens are configured (local/dev), the API is
    open on localhost exactly as in v1.1."""
    request.state.member = None
    if MEMBER_BY_TOKEN and request.url.path.startswith("/api"):
        member = _member_of(request)
        if member is None:
            return Response('{"detail": "missing or bad X-W2-Token"}', 401,
                            media_type="application/json")
        request.state.member = member
    return await call_next(request)


def _save_upload(dest: Path, f: UploadFile) -> str:
    name = Path(f.filename or "upload.md").name
    (dest / name).write_bytes(f.file.read())
    return name


@app.post("/api/runs")
def create_run(request: Request,
               brd: UploadFile = File(...),
               sdd_1: UploadFile = File(...),
               sdd_2: UploadFile | None = File(None),
               zenagent_is: str = Form("a"),
               live_evidence: bool = Form(False),
               auto_approve_checkpoint: bool = Form(True),
               evaluator_model: str = Form(None)):
    # v2.0 defaults (PRD D5/D12, FR-1): hands-free auto-approve is the default;
    # the judging label is the fixed panel in dual-judge mode.
    if evaluator_model is None:
        evaluator_model = ("panel:claude-code+gemini"
                           if EVAL_PROTOCOL == "dual-judge"
                           else "claude-code-subscription")
    mode = "A" if sdd_2 is not None else "B"
    if mode == "A" and zenagent_is not in ("a", "b"):
        raise HTTPException(400, "zenagent_is must be 'a' or 'b'")
    run_id = new_run_id(mode)
    rd = run_dir(run_id)
    (rd / "inputs").mkdir(parents=True)
    files = {"brd": _save_upload(rd / "inputs", brd),
             "sdd_1": _save_upload(rd / "inputs", sdd_1)}
    if sdd_2 is not None:
        files["sdd_2"] = _save_upload(rd / "inputs", sdd_2)
    state = {"run_id": run_id, "mode": mode, "status": "created",
             "stage": "S0", "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "files": files, "zenagent_is": zenagent_is,
             "live_evidence": bool(live_evidence),
             "auto_approve_checkpoint": bool(auto_approve_checkpoint),
             "evaluator_model": evaluator_model,
             "protocol": EVAL_PROTOCOL,
             # FR-13 owner-pays affinity: the uploader's seat runs this deal.
             "owner": getattr(request.state, "member", None) or "operator",
             "digests": {}, "checkpoint_approved": False}
    save_state(run_id, state)
    st = orchestrator.advance(run_id)
    return {"run_id": run_id, "mode": mode, "status": st["status"]}


@app.get("/api/runs")
def runs():
    out = list_runs()
    for r in out:
        try:
            r["usage"] = packets.usage_totals(run_dir(r["run_id"]))
        except Exception:
            pass
    return out


@app.get("/api/runs/{run_id}")
def run_state(run_id: str):
    try:
        st = public_state(run_id)
    except FileNotFoundError:
        raise HTTPException(404, "run not found")
    st["open_packets"] = [{k: p[k] for k in ("packet_id", "kind", "label",
                                             "needs_web", "claimed_by")}
                          for p in packets.open_packets(run_dir(run_id))]
    st["usage"] = packets.usage_totals(run_dir(run_id))
    return st


@app.post("/api/runs/{run_id}/approve")
def approve(run_id: str, body: dict):
    st = load_state(run_id)
    if st["status"] != "awaiting_checkpoint":
        raise HTTPException(409, f"run is {st['status']}, not awaiting_checkpoint")
    if not body.get("approve"):
        st["status"] = "stopped"
        st["stop_reason"] = body.get("reason", "operator stop at D.5")
        save_state(run_id, st)
        return {"status": "stopped"}
    st["checkpoint_approved"] = True
    st["checkpoint_approved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_state(run_id, st)
    return orchestrator.advance(run_id) | {"note": "proceeding past D.5"}


@app.get("/api/runs/{run_id}/download/{key}")
def download(run_id: str, key: str):
    p = resolve_download(run_id, key)
    if not p:
        raise HTTPException(404, "artifact not available")
    return FileResponse(p, filename=p.name)


@app.get("/api/packets/next")
def next_packet(request: Request, runner_id: str = Query(...),
                engine: str = Query(None)):
    """Claim the next open packet (FIFO by run) — restricted to runs whose
    owner matches the presenting member (FR-13 owner-pays affinity; stale
    claims are only ever taken over by the same owner's runners, because no
    other member's runner is offered them). Every call doubles as the
    presenting member's heartbeat (Application Flow §6)."""
    member = getattr(request.state, "member", None)
    _heartbeat(member, runner_id, engine)
    for r in list_runs():
        if r["status"] not in ("awaiting_packets", "running"):
            continue
        if MEMBER_BY_TOKEN and member and (r.get("owner") or "operator") != member:
            continue  # another member's deal; their seat pays for it
        rd = run_dir(r["run_id"])
        for p in packets.open_packets(rd):
            stale = packets.claim_is_stale(p)
            if p.get("claimed_by") in (None, runner_id) or stale:
                d = packets.claim(rd, p["packet_id"], runner_id)
                d["run_id"] = r["run_id"]
                return d
    return JSONResponse({"packet_id": None}, status_code=200)


@app.get("/api/runners")
def runners_status():
    """Heartbeat ledger (TR-29): powers the console's 'your runner: connected
    · last seen Ns ago' card."""
    return sorted(RUNNERS.values(), key=lambda r: r.get("member", ""))


@app.post("/api/packets/{run_id}/{pid}/result")
def post_result(run_id: str, pid: str, body: dict):
    rd = run_dir(run_id)
    if not packets.exists(rd, pid):
        raise HTTPException(404, "unknown packet")
    if "result" not in body or not isinstance(body["result"], dict):
        raise HTTPException(400, "body must be {result: {...}, usage: {...}}")
    # Write-once (Flow §8 / TR-5): a duplicate POST after a completed result
    # is acknowledged and ignored — never overwritten.
    if packets.result_path(rd, pid).exists():
        st = load_state(run_id)
        return {"status": st["status"], "stage": st.get("stage"),
                "note": "duplicate result ignored (write-once)"}
    usage = body.get("usage") or {}
    # BILLING TRIPWIRE (server side, defense in depth): a subscription-executed
    # packet must never report a billable dollar cost. Any nonzero cost means
    # the runner's environment fell back to API billing -> halt the run loudly.
    if float(usage.get("total_cost_usd") or 0.0) > 0:
        st = load_state(run_id)
        st["status"] = "error"
        st["error"] = ("BILLING_TRIPWIRE: packet result reported a nonzero API cost "
                       f"({usage.get('total_cost_usd')}). The runner must authenticate "
                       "with the Claude subscription only. Run halted; no result stored.")
        save_state(run_id, st)
        raise HTTPException(402, st["error"])
    # Shape validation (TR-15 / risk R-3): malformed results are refused and
    # never stored — the packet stays open and the runner retries fresh.
    packet = json.loads(packets.packet_path(rd, pid).read_text())
    problem = (packet_shapes.validate_result(packet.get("kind"), body["result"],
                                             packet.get("meta"))
               or packet_shapes.validate_judge_provenance(
                   packet.get("kind"), packet.get("meta"), usage))
    if problem:
        st = load_state(run_id)
        st["last_rejected_result"] = {"packet_id": pid, "reason": problem,
                                      "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        save_state(run_id, st)
        raise HTTPException(400, f"result rejected ({pid}): {problem}")
    packets.complete(rd, pid, body["result"], usage)
    st = orchestrator.advance(run_id)
    return {"status": st["status"], "stage": st.get("stage")}


app.mount("/", StaticFiles(directory=str(Path(__file__).parent / "static"),
                           html=True), name="static")
