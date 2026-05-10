"""Weekly Deep Audit — health-check sweep across the whole stack.

Per spec §11 / ARCHITECTURE Batch 7.

Findings categories:

    GATE_FAIL        — recent reasoning chains with overall=fail
    STALE_SUGGESTION — pending suggestions older than 14 days
    LOW_GATE_SCORE   — reasoning chains with mean gate score < 0.5
    DEAD_LIFECYCLE   — subcaps that landed in DEAD state
    OPEN_FLAGS       — flag rows with status=OPEN
    HIGH_COST_DAY    — daily LLM spend > 80% of cost ceiling

Each finding gets a severity (`critical | warn | info`) and a reference
back to the source row so reviewers can drill in.

Audit reports are append-only (`audit_reports` collection) so the QA &
Audit Dashboard (Batch 8) can show history over time.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import get_settings
from .repository import get_repository

logger = logging.getLogger(__name__)

REPORTS_COLLECTION = "audit_reports"

SEVERITY_CRITICAL = "critical"
SEVERITY_WARN = "warn"
SEVERITY_INFO = "info"


@dataclass
class Finding:
    kind: str
    severity: str
    title: str
    detail: str
    ref_collection: str | None = None
    ref_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditReport:
    report_id: str
    started_at: str
    completed_at: str
    findings: list[dict]
    summary: dict[str, int]  # severity → count
    inputs_seen: dict[str, int]


# ─── Sweeps ─────────────────────────────────────────────────────────────────


def _sweep_gates() -> list[Finding]:
    repo = get_repository()
    out: list[Finding] = []
    chains = list(repo.list("reasoning_chains"))
    chains.sort(key=lambda c: c.get("started_at", ""), reverse=True)
    for c in chains[:50]:
        overall = c.get("overall")
        score = (c.get("gates") or {}).get("score") or 0
        if overall == "fail":
            out.append(Finding(
                kind="GATE_FAIL",
                severity=SEVERITY_CRITICAL,
                title=f"Chain {c.get('chain_id', '?')[-8:]} failed gates",
                detail=f"Overall verdict=fail; gate score {score:.2f}.",
                ref_collection="reasoning_chains",
                ref_id=c.get("chain_id"),
            ))
        elif overall == "warn" and score < 0.5:
            out.append(Finding(
                kind="LOW_GATE_SCORE",
                severity=SEVERITY_WARN,
                title=f"Chain {c.get('chain_id', '?')[-8:]} low gate score",
                detail=f"Score {score:.2f} below 0.50 threshold.",
                ref_collection="reasoning_chains",
                ref_id=c.get("chain_id"),
            ))
    return out


def _sweep_stale_suggestions(*, max_age_days: int = 14) -> list[Finding]:
    repo = get_repository()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    out: list[Finding] = []
    for s in repo.list("suggestions"):
        if s.get("status") != "pending":
            continue
        created = _parse_iso(s.get("created_at"))
        if created and created < cutoff:
            age = (datetime.now(timezone.utc) - created).days
            out.append(Finding(
                kind="STALE_SUGGESTION",
                severity=SEVERITY_WARN,
                title=f"Pending suggestion {s.get('id', '?')[-12:]} aged {age}d",
                detail=f"Kind={s.get('kind')} target={s.get('target')}; "
                       f"created {s.get('created_at')}.",
                ref_collection="suggestions",
                ref_id=s.get("id"),
                metadata={"age_days": age},
            ))
    return out


def _sweep_dead_subcaps() -> list[Finding]:
    repo = get_repository()
    out: list[Finding] = []
    for s in repo.list("lifecycle_scores"):
        if s.get("state") != "DEAD":
            continue
        out.append(Finding(
            kind="DEAD_LIFECYCLE",
            severity=SEVERITY_INFO,
            title=f"Subcap {s.get('sub_cap_id')} in DEAD state",
            detail=f"{s.get('sub_cap_name', '')} has no live evidence; "
                   "candidate for retirement.",
            ref_collection="lifecycle_scores",
            ref_id=s.get("sub_cap_id"),
        ))
    return out


def _sweep_flags() -> list[Finding]:
    repo = get_repository()
    out: list[Finding] = []
    for f in repo.list("flags"):
        status = (f.get("status") or "").lower()
        if status not in ("", "open"):
            continue
        out.append(Finding(
            kind="OPEN_FLAGS",
            severity=SEVERITY_WARN,
            title=f"Flag {f.get('flag_id', '?')}",
            detail=f.get("message") or f.get("kind") or "Open change-flag.",
            ref_collection="flags",
            ref_id=f.get("flag_id"),
        ))
    return out


def _sweep_cost() -> list[Finding]:
    s = get_settings()
    if s.daily_spend_ceiling_usd <= 0:
        return []
    from .llm.cost_tracker import CostTracker

    tracker = CostTracker()
    spent = tracker.spend_today()
    cap = s.daily_spend_ceiling_usd
    pct = spent / cap if cap else 0
    if pct >= 0.8:
        sev = SEVERITY_CRITICAL if pct >= s.cost_throttle_pct else SEVERITY_WARN
        return [Finding(
            kind="HIGH_COST_DAY",
            severity=sev,
            title=f"Daily LLM spend at {pct * 100:.0f}% of ${cap:.2f}",
            detail=f"Today: ${spent:.2f} (ceiling ${cap:.2f}); "
                   f"throttle at {s.cost_throttle_pct * 100:.0f}%.",
            ref_collection="llm_costs",
            ref_id=None,
            metadata={"spent_usd": spent, "ceiling_usd": cap},
        )]
    return []


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# ─── Public API ─────────────────────────────────────────────────────────────


def run_audit() -> AuditReport:
    started = datetime.now(timezone.utc)
    repo = get_repository()

    findings = (
        _sweep_gates()
        + _sweep_stale_suggestions()
        + _sweep_dead_subcaps()
        + _sweep_flags()
        + _sweep_cost()
    )

    summary: dict[str, int] = {SEVERITY_CRITICAL: 0, SEVERITY_WARN: 0, SEVERITY_INFO: 0}
    for f in findings:
        summary[f.severity] = summary.get(f.severity, 0) + 1

    inputs_seen = {
        "reasoning_chains": len(repo.list("reasoning_chains")),
        "suggestions": len(repo.list("suggestions")),
        "lifecycle_scores": len(repo.list("lifecycle_scores")),
        "flags": len(repo.list("flags")),
    }

    completed = datetime.now(timezone.utc)
    # microsecond precision so back-to-back audits don't collide on the same id
    report_id = f"audit-{int(started.timestamp() * 1_000_000)}"
    report = AuditReport(
        report_id=report_id,
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        findings=[asdict(f) for f in findings],
        summary=summary,
        inputs_seen=inputs_seen,
    )
    repo.upsert(REPORTS_COLLECTION, report_id, asdict(report))
    return report


def list_reports(limit: int = 50) -> list[dict]:
    items = list(get_repository().list(REPORTS_COLLECTION))
    items.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return items[:limit]


def get_report(report_id: str) -> dict | None:
    return get_repository().get(REPORTS_COLLECTION, report_id)


def latest_report() -> dict | None:
    items = list_reports(limit=1)
    return items[0] if items else None
