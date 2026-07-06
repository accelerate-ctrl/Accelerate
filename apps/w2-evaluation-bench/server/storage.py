"""Run storage: one directory per run (mirrors the engine's /pilot-runs layout),
with state.json as the orchestrator's durable state machine record."""
from __future__ import annotations
import json
import time
import uuid
from pathlib import Path

from .config import RUNS_DIR, ESCROW_NAME

# Artifacts the UI may download. The escrow and raw packet payloads are NOT here.
DOWNLOADABLE = {
    "report": ["diagnostic-report.docx", "sdd-review-report.docx"],
    "score_sheet_a": ["output-a-score-sheet.xlsx"],
    "score_sheet_b": ["output-b-score-sheet.xlsx"],
    "content_mapping": ["content-mapping.xlsx"],
    "release_a": ["release-awareness-A.json"],
    "release_b": ["release-awareness-B.json"],
    "lift": ["lift-calc.json"],
    "run_record": ["run-record.json"],
    "diagnostic_bundle": ["diagnostic-bundle.json"],
}


def new_run_id(mode: str) -> str:
    return f"W2-{time.strftime('%Y%m%d-%H%M%S')}-{mode}-{uuid.uuid4().hex[:6]}"


def run_dir(run_id: str) -> Path:
    p = (RUNS_DIR / run_id).resolve()
    if RUNS_DIR.resolve() not in p.parents:
        raise ValueError("bad run id")
    return p


def state_path(run_id: str) -> Path:
    return run_dir(run_id) / "state.json"


def load_state(run_id: str) -> dict:
    return json.loads(state_path(run_id).read_text())


def save_state(run_id: str, state: dict) -> None:
    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    state_path(run_id).write_text(json.dumps(state, indent=2))


def list_runs() -> list[dict]:
    out = []
    for d in sorted(RUNS_DIR.iterdir(), reverse=True):
        sp = d / "state.json"
        if sp.exists():
            s = json.loads(sp.read_text())
            out.append({k: s.get(k) for k in
                        ("run_id", "mode", "status", "created_at", "updated_at",
                         "stage", "error", "usage", "owner", "protocol")})
    return out


def public_state(run_id: str) -> dict:
    """State view for the UI — escrow-free by construction."""
    s = load_state(run_id)
    s.pop("escrow_note", None)
    rd = run_dir(run_id)
    s["artifacts"] = {k: names[0] for k, names in DOWNLOADABLE.items()
                      if any((rd / n).exists() for n in names)}
    return s


def resolve_download(run_id: str, key: str) -> Path | None:
    names = DOWNLOADABLE.get(key)
    if not names:
        return None
    rd = run_dir(run_id)
    for n in names:
        p = rd / n
        if p.exists() and p.name != ESCROW_NAME:
            return p
    return None
