"""TRD §10 — Service-Level Objectives + alert rule catalogue.

The TRD enumerates SLOs for the five top user-facing surfaces:
``health``, ``catalogue ingest``, ``chat``, ``graph``, and ``digest``.
Each SLO ships with two burn-rate windows (fast = 1h, slow = 24h) and a
severity that maps cleanly to PagerDuty / on-call routing.

This module is the single source of truth for those rules. It is used in
two places:

1. CI: :func:`render_alert_policies` emits the Cloud Monitoring v3 alert
   policy bodies for ``terraform apply`` — that keeps the production
   alert configuration co-located with the code that defines the SLO.
2. Tests + runtime: :func:`evaluate_slo` takes a sample window (e.g.
   {"good": 980, "total": 1000, "latency_p95_ms": 1400}) and returns a
   :class:`SLOEvaluation` that the dashboard tile and the alert engine
   can both consume.

The intent is *not* to replace Cloud Monitoring — we still let GCP do the
sliding-window math. The intent is to keep the SLO definitions reviewable
in code, with tests that catch typos before alerts go silent.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class AlertSeverity(str, Enum):
    PAGE = "page"           # wakes the on-call engineer
    TICKET = "ticket"       # opens a P3 ticket for the next business day
    INFO = "info"           # dashboard only, no notification


@dataclass(frozen=True)
class BurnRateWindow:
    """A fast/slow window pair per the SRE workbook formula.

    ``error_budget_fraction`` is the fraction of the monthly error budget
    that, if burned within ``lookback_minutes``, triggers the alert.
    1h-fast at 14.4× budget and 24h-slow at 1.0× budget are the standard
    multi-window multi-burn-rate rules from Google SRE workbook §5.
    """
    lookback_minutes: int
    error_budget_fraction: float


@dataclass(frozen=True)
class SLODefinition:
    slo_id: str
    surface: str  # health | catalogue | chat | graph | digest
    sli_name: str
    target_ratio: float       # e.g. 0.999 → 99.9% of requests must be "good"
    latency_p95_ms: int | None = None
    latency_p99_ms: int | None = None
    description: str = ""
    fast_window: BurnRateWindow = BurnRateWindow(lookback_minutes=60, error_budget_fraction=0.02)
    slow_window: BurnRateWindow = BurnRateWindow(lookback_minutes=1440, error_budget_fraction=0.05)
    severity: AlertSeverity = AlertSeverity.TICKET


@dataclass
class SLOAlert:
    """A render-time policy that ``terraform apply`` would push to GCP."""
    slo_id: str
    name: str
    window: str  # "fast" | "slow"
    severity: str
    lookback_minutes: int
    threshold_burn_rate: float
    target_ratio: float
    documentation: str


@dataclass
class SLOEvaluation:
    slo_id: str
    surface: str
    sli_name: str
    good: int
    total: int
    actual_ratio: float
    target_ratio: float
    in_compliance: bool
    error_budget_used: float
    latency_p95_ms: int | None = None
    latency_p99_ms: int | None = None
    latency_breach: bool = False
    notes: list[str] = field(default_factory=list)


# ─── Registry ───────────────────────────────────────────────────────────────


# Pulled verbatim from TRD §10 table:
#   /api/health           99.95%   <300ms p95
#   catalogue ingest      99.0%    <30min p95
#   chat (FR-16)          99.5%    <2s p95 first token
#   graph path / centrality 99.0%  <1s p95
#   quarterly digest      99.0%    SLOs evaluated per run, not per request
SLO_REGISTRY: dict[str, SLODefinition] = {
    "health": SLODefinition(
        slo_id="health",
        surface="health",
        sli_name="probe_success_ratio",
        target_ratio=0.9995,
        latency_p95_ms=300,
        description="/api/health probe must succeed 99.95% of the time; p95 <300ms.",
        severity=AlertSeverity.PAGE,
    ),
    "catalogue_ingest": SLODefinition(
        slo_id="catalogue_ingest",
        surface="catalogue",
        sli_name="ingest_success_ratio",
        target_ratio=0.99,
        latency_p95_ms=30 * 60 * 1000,  # 30min in ms
        description="Pillar workbook upload completes successfully 99% of the time; p95 <30min.",
        severity=AlertSeverity.TICKET,
    ),
    "chat_first_token": SLODefinition(
        slo_id="chat_first_token",
        surface="chat",
        sli_name="chat_success_ratio",
        target_ratio=0.995,
        latency_p95_ms=2000,
        description="Chat SSE stream emits first token <2s p95 with 99.5% success.",
        severity=AlertSeverity.PAGE,
    ),
    "graph_query": SLODefinition(
        slo_id="graph_query",
        surface="graph",
        sli_name="graph_query_success_ratio",
        target_ratio=0.99,
        latency_p95_ms=1000,
        description="Shortest-path + centrality queries return <1s p95 with 99% success.",
        severity=AlertSeverity.TICKET,
    ),
    "digest_run": SLODefinition(
        slo_id="digest_run",
        surface="digest",
        sli_name="digest_run_success_ratio",
        target_ratio=0.99,
        latency_p95_ms=None,
        description="Quarterly digest checkpoint pipeline finishes within budget 99% of runs.",
        severity=AlertSeverity.TICKET,
    ),
}


# ─── API ────────────────────────────────────────────────────────────────────


def list_slos() -> list[dict[str, Any]]:
    return [_slo_to_dict(s) for s in SLO_REGISTRY.values()]


def _slo_to_dict(s: SLODefinition) -> dict[str, Any]:
    return {
        "slo_id": s.slo_id,
        "surface": s.surface,
        "sli_name": s.sli_name,
        "target_ratio": s.target_ratio,
        "latency_p95_ms": s.latency_p95_ms,
        "latency_p99_ms": s.latency_p99_ms,
        "description": s.description,
        "fast_window": asdict(s.fast_window),
        "slow_window": asdict(s.slow_window),
        "severity": s.severity.value,
    }


MONTH_MINUTES = 30 * 24 * 60  # 43,200


def list_alerts() -> list[SLOAlert]:
    """Two alerts per SLO — one fast burn (page) and one slow burn (ticket).

    Burn rate is the multi-window MWMBR value from the Google SRE workbook
    §5: ``error_budget_fraction / (lookback_minutes / month_minutes)`` —
    i.e. how many "monthly rates" of error budget the window is consuming.
    A fast 1h window at 2% budget = 14.4× sustainable; a slow 24h window
    at 5% = 1.5× sustainable.
    """
    alerts: list[SLOAlert] = []
    for slo in SLO_REGISTRY.values():
        for window_name, window in (("fast", slo.fast_window), ("slow", slo.slow_window)):
            window_fraction = window.lookback_minutes / MONTH_MINUTES
            burn_rate = (
                window.error_budget_fraction / window_fraction
                if window_fraction > 0
                else float("inf")
            )
            severity = slo.severity if window_name == "fast" else AlertSeverity.TICKET
            alerts.append(SLOAlert(
                slo_id=slo.slo_id,
                name=f"{slo.slo_id}.{window_name}_burn",
                window=window_name,
                severity=severity.value,
                lookback_minutes=window.lookback_minutes,
                threshold_burn_rate=round(burn_rate, 2),
                target_ratio=slo.target_ratio,
                documentation=slo.description,
            ))
    return alerts


def render_alert_policies() -> list[dict[str, Any]]:
    """Serialised payloads for terraform / Cloud Monitoring v3 import."""
    return [asdict(a) for a in list_alerts()]


def evaluate_slo(
    slo_id: str,
    *,
    good: int,
    total: int,
    latency_p95_ms: int | None = None,
    latency_p99_ms: int | None = None,
) -> SLOEvaluation:
    """Score a sample window against the SLO."""
    if slo_id not in SLO_REGISTRY:
        raise KeyError(slo_id)
    slo = SLO_REGISTRY[slo_id]
    if total < 0 or good < 0 or good > total:
        raise ValueError(
            f"invalid sample: good={good}, total={total} (good must be in [0, total])"
        )
    ratio = good / total if total > 0 else 1.0
    in_compliance = ratio >= slo.target_ratio
    budget = max(1e-9, 1 - slo.target_ratio)
    error_budget_used = max(0.0, min(1.0, (1 - ratio) / budget))
    latency_breach = False
    notes: list[str] = []
    if slo.latency_p95_ms is not None and latency_p95_ms is not None:
        if latency_p95_ms > slo.latency_p95_ms:
            latency_breach = True
            notes.append(
                f"p95 {latency_p95_ms}ms exceeds target {slo.latency_p95_ms}ms"
            )
    if slo.latency_p99_ms is not None and latency_p99_ms is not None:
        if latency_p99_ms > slo.latency_p99_ms:
            latency_breach = True
            notes.append(
                f"p99 {latency_p99_ms}ms exceeds target {slo.latency_p99_ms}ms"
            )
    if not in_compliance:
        notes.append(
            f"availability {ratio:.4f} below target {slo.target_ratio:.4f}"
        )
    return SLOEvaluation(
        slo_id=slo.slo_id,
        surface=slo.surface,
        sli_name=slo.sli_name,
        good=good,
        total=total,
        actual_ratio=round(ratio, 6),
        target_ratio=slo.target_ratio,
        in_compliance=in_compliance,
        error_budget_used=round(error_budget_used, 4),
        latency_p95_ms=latency_p95_ms,
        latency_p99_ms=latency_p99_ms,
        latency_breach=latency_breach,
        notes=notes,
    )


def dump_registry_json() -> str:
    """Helper used by ``infra/`` scripts to bake the registry into terraform."""
    return json.dumps(
        {
            "slos": list_slos(),
            "alert_policies": render_alert_policies(),
        },
        indent=2,
    )
