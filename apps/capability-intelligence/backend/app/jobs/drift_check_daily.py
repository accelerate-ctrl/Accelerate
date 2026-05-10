"""Cloud Run Job: drift_check_daily.

Looks for unusual lifecycle transitions (anything other than the
adjacent-state pairs RISING↔STABLE, EMERGING↔RISING, etc.) in the last
24h. Surfaces transitions that skip multiple states (e.g.,
RISING → DEAD) as drift findings; persisted to the audit_reports
collection for the following week's deep-audit roll-up.

Daily cadence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..services.repository import get_repository

ADJACENT = {
    ("EMERGING", "RISING"), ("RISING", "EMERGING"),
    ("RISING", "STABLE"), ("STABLE", "RISING"),
    ("STABLE", "DECLINING"), ("DECLINING", "STABLE"),
    ("DECLINING", "FADING"), ("FADING", "DECLINING"),
    ("FADING", "DEAD"), ("DEAD", "FADING"),
    ("EMERGING", "DEAD"), ("DEAD", "EMERGING"),
}


def run() -> dict:
    repo = get_repository()
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    drift: list[dict] = []
    for t in repo.list("lifecycle_transitions"):
        try:
            ts = datetime.fromisoformat((t.get("transitioned_at") or "").replace("Z", "+00:00"))
        except Exception:
            continue
        if ts < cutoff:
            continue
        pair = (t.get("from_state"), t.get("to_state"))
        if pair not in ADJACENT and pair[0] is not None and pair[1] is not None:
            drift.append({
                "sub_cap_id": t.get("sub_cap_id"),
                "from_state": pair[0],
                "to_state": pair[1],
                "transitioned_at": t.get("transitioned_at"),
            })
    return {"drift_count": len(drift), "drift": drift[:50]}
