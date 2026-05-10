"""Cloud Run Job: deep_audit_weekly.

Runs the Batch-7 deep-audit sweep + Batch-8 notifications refresh in
sequence. Weekly cadence. Emits one ``audit.critical_finding`` event
for any critical-severity finding so on-call can be paged.
"""

from __future__ import annotations

from dataclasses import asdict

from ..services import audit_service, notifications_service
from ..services.event_bus import publish_event


def run() -> dict:
    audit = audit_service.run_audit()
    notifications_service.refresh()
    if audit.summary.get("critical", 0) > 0:
        critical = [f for f in audit.findings if f.get("severity") == "critical"]
        publish_event(
            "audit.critical_finding",
            {
                "report_id": audit.report_id,
                "critical_count": audit.summary["critical"],
                "kinds": sorted({f.get("kind") for f in critical if f.get("kind")}),
            },
        )
    return asdict(audit)
