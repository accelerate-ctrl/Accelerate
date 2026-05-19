"""Observability — SLO alert rule registry (TRD §10).

Phase 5 deliverable. The legacy :mod:`app.observability` module owns the
OpenTelemetry middleware + structured logger. This package adds the SLO
catalogue used by Cloud Monitoring alert policies and the SRE dashboard.
"""

from .slos import (
    SLO_REGISTRY,
    AlertSeverity,
    BurnRateWindow,
    SLOAlert,
    SLODefinition,
    SLOEvaluation,
    evaluate_slo,
    list_alerts,
    list_slos,
    render_alert_policies,
)

__all__ = [
    "SLO_REGISTRY",
    "AlertSeverity",
    "BurnRateWindow",
    "SLOAlert",
    "SLODefinition",
    "SLOEvaluation",
    "evaluate_slo",
    "list_alerts",
    "list_slos",
    "render_alert_policies",
]
