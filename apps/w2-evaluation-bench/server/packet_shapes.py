"""packet_shapes.py — server-side structural validation of packet RESULTS at
POST time (TRD TR-15 + risk register R-3: "Gemini JSON discipline").

A malformed result is REJECTED with HTTP 400 and never stored, so the packet
stays open and the runner retries with a fresh model call — the run never
advances on garbage, and provenance never lies. Checks here are STRUCTURAL
(shapes, vocabularies, required fields); semantic checks live in the
consensus engine (merge bounds) and the R1–R28 validator.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "engine" / "evaluate-sdd" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import contracts  # noqa: E402

RULINGS = ("adopt_claude", "adopt_gemini", "meet_between", "dissent")


def _err(msg: str) -> str:
    return msg


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_result(kind: str, result: dict, meta: dict | None = None):
    """Return an error string when the result is structurally invalid for the
    packet kind; None when acceptable. Unknown kinds pass (forward-compat)."""
    if not isinstance(result, dict):
        return _err("result must be a JSON object")
    meta = meta or {}

    if kind == "pass":
        for key in ("dim_scores", "sub_scores", "verdicts"):
            if not isinstance(result.get(key), dict):
                return _err(f"pass result missing object field {key!r}")
        for d, v in result["dim_scores"].items():
            if not _is_num(v):
                return _err(f"pass result dim_scores[{d!r}] is not numeric: {v!r}")
        for d, subs in result["sub_scores"].items():
            if not isinstance(subs, dict):
                return _err(f"pass result sub_scores[{d!r}] is not an object")
            for k, v in subs.items():
                if not _is_num(v):
                    return _err(f"pass result sub_scores[{d!r}][{k!r}] is not numeric: {v!r}")
        for cid, rec in result["verdicts"].items():
            if not isinstance(rec, dict):
                return _err(f"pass result verdicts[{cid!r}] is not an object")
            if rec.get("verdict") not in contracts.VALID_VERDICTS:
                return _err(f"pass result verdicts[{cid!r}].verdict "
                            f"{rec.get('verdict')!r} not in {sorted(contracts.VALID_VERDICTS)}")
        return None

    if kind == "reconcile":
        rulings = result.get("rulings")
        if not isinstance(rulings, dict):
            return _err("reconcile result missing object field 'rulings'")
        for key, r in rulings.items():
            if not isinstance(r, dict):
                return _err(f"rulings[{key!r}] is not an object")
            if r.get("ruling") not in RULINGS:
                return _err(f"rulings[{key!r}].ruling {r.get('ruling')!r} "
                            f"not in {RULINGS}")
            if r["ruling"] != "dissent" and not r.get("citation"):
                return _err(f"rulings[{key!r}] ({r['ruling']}) missing the required "
                            "verbatim SDD citation")
            if r["ruling"] == "meet_between" and r.get("value") in (None, {}):
                return _err(f"rulings[{key!r}] meet_between missing its 'value'")
        return None

    if kind == "review":
        for key in ("findings", "recommendations"):
            if not isinstance(result.get(key), list):
                return _err(f"review result missing list field {key!r}")
        for i, f in enumerate(result["findings"]):
            if not isinstance(f, dict):
                return _err(f"review findings[{i}] is not an object")
            if f.get("verdict") not in ("strength", "gap", "risk"):
                return _err(f"review findings[{i}].verdict {f.get('verdict')!r} "
                            "not in (strength/gap/risk)")
        return None

    if kind == "components":
        if not isinstance(result.get("components"), list):
            return _err("components result missing list field 'components'")
        return None

    if kind == "features":
        if not isinstance(result.get("features"), list):
            return _err("features result missing list field 'features'")
        return None

    if kind == "narrative":
        for key in ("per_dim_key_reasoning", "narrative_per_dim",
                    "zms_calibration_citations"):
            if not isinstance(result.get(key), dict):
                return _err(f"narrative result missing object field {key!r}")
        return None

    if kind == "exec_narrative":
        if not isinstance(result.get("exec_narrative"), dict):
            return _err("exec_narrative result missing object field 'exec_narrative'")
        return None

    if kind == "evidence":
        if not isinstance(result.get("evidence"), dict):
            return _err("evidence result missing object field 'evidence'")
        return None

    return None  # unknown kind: forward-compatible


def validate_judge_provenance(kind: str, meta: dict | None, usage: dict | None):
    """TR-8 provenance integrity: when the runner reports which judge executed
    a routed packet, it must match the judge the packet was addressed to. A
    silent judge swap would make every provenance field downstream a lie."""
    meta, usage = meta or {}, usage or {}
    expected = meta.get("judge")
    reported = usage.get("judge")
    if kind in ("pass", "review", "reconcile") and expected and reported \
            and reported != expected:
        return _err(f"packet was addressed to judge {expected!r} but the runner "
                    f"reported execution by {reported!r} — refusing the result "
                    "(judge provenance integrity, TR-8)")
    return None
