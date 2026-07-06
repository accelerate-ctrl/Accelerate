"""Work-packet store. Packets live under <run>/packets/ as
<pid>.packet.json (prompt + metadata) and <pid>.result.json (runner output).
The claim/complete protocol is deliberately simple: file-based, idempotent,
auditable. Usage reported by the runner is accumulated on the run state so the
operator can watch subscription-credit consumption per run."""
from __future__ import annotations
import json
import re
import time
from pathlib import Path

SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _pdir(rd: Path) -> Path:
    d = rd / "packets"
    d.mkdir(exist_ok=True)
    return d


def _fname(pid: str) -> str:
    return SAFE.sub("_", pid)


def packet_path(rd: Path, pid: str) -> Path:
    return _pdir(rd) / f"{_fname(pid)}.packet.json"


def result_path(rd: Path, pid: str) -> Path:
    return _pdir(rd) / f"{_fname(pid)}.result.json"


def exists(rd: Path, pid: str) -> bool:
    return packet_path(rd, pid).exists()


def create(rd: Path, pid: str, *, kind: str, label: str, prompt: str,
           meta: dict | None = None, schema_hint: dict | None = None,
           needs_web: bool = False) -> None:
    packet_path(rd, pid).write_text(json.dumps({
        "packet_id": pid, "kind": kind, "label": label, "prompt": prompt,
        "meta": meta or {}, "schema_hint": schema_hint, "needs_web": needs_web,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "claimed_by": None, "claimed_at": None,
    }, indent=2))


def open_packets(rd: Path) -> list[dict]:
    out = []
    for p in sorted(_pdir(rd).glob("*.packet.json")):
        rid = p.name.replace(".packet.json", "")
        if not (p.parent / f"{rid}.result.json").exists():
            out.append(json.loads(p.read_text()))
    return out


def claim(rd: Path, pid: str, runner_id: str) -> dict:
    p = packet_path(rd, pid)
    d = json.loads(p.read_text())
    d["claimed_by"] = runner_id
    d["claimed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    p.write_text(json.dumps(d, indent=2))
    return d


def complete(rd: Path, pid: str, result: dict, usage: dict | None = None) -> None:
    result_path(rd, pid).write_text(json.dumps(
        {"result": result, "usage": usage or {},
         "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=2))


def result(rd: Path, pid: str) -> dict:
    return json.loads(result_path(rd, pid).read_text())["result"]


def usage_totals(rd: Path) -> dict:
    tot = {"packets": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd_reported": 0.0}
    for p in _pdir(rd).glob("*.result.json"):
        d = json.loads(p.read_text())
        u = d.get("usage") or {}
        tot["packets"] += 1
        tot["input_tokens"] += int(u.get("input_tokens") or 0)
        tot["output_tokens"] += int(u.get("output_tokens") or 0)
        tot["cost_usd_reported"] += float(u.get("total_cost_usd") or 0.0)
    return tot


def claim_is_stale(packet: dict, ttl_seconds: int = 90) -> bool:
    """A claim older than ttl with no result is presumed dead (runner crashed)."""
    ts = packet.get("claimed_at")
    if not packet.get("claimed_by") or not ts:
        return False
    try:
        then = time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return True
    return (time.time() - then) > ttl_seconds
