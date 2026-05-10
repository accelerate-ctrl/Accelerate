"""Cloud Run Job: eval_run_weekly.

Runs the Batch-8 eval harness against every persisted golden dataset.
Weekly cadence. Mean scores below the alert threshold trigger an
`audit.critical_finding`-style escalation via the audit service in the
following week's deep-audit job.
"""

from __future__ import annotations

from ..services import eval_service


def run() -> dict:
    return eval_service.run_eval()
