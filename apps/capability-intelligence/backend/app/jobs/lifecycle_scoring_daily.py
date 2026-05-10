"""Cloud Run Job: lifecycle_scoring_daily.

Recomputes Batch 6 lifecycle scores against the current state of every
input collection. Daily cadence. Emits one ``lifecycle.transitioned``
event per state change so downstream consumers (notifications,
suggestions) can react.
"""

from __future__ import annotations

from dataclasses import asdict

from ..services import lifecycle_service
from ..services.event_bus import publish_event


def run() -> dict:
    summary = lifecycle_service.recompute_all()
    if summary.transitions > 0:
        publish_event(
            "lifecycle.transitioned",
            {
                "run_id": summary.run_id,
                "transitions": summary.transitions,
                "state_distribution": summary.state_distribution,
            },
        )
    return asdict(summary)
