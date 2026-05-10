"""In-app notifications fed from audit + lifecycle + suggestions.

Per spec §16 / ARCHITECTURE Batch 8.

Notification kinds (each mapped to a Batch 6/7 source row):

    AUDIT_CRITICAL        critical finding from the latest audit
    AUDIT_WARN            warn finding (e.g., stale suggestion)
    LIFECYCLE_TRANSITION  any state change in the last 7 days
    SUGGESTION_PENDING    new pending suggestion needing review
    GATE_REGRESSION       chain whose latest run flipped from pass→fail

Notifications carry a `read` flag. The dashboard surfaces unread
critical first, then warn, then info (pure UI sort).
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .repository import get_repository

logger = logging.getLogger(__name__)

NOTIFICATIONS_COLLECTION = "notifications"
RUN_COLLECTION = "notification_runs"


@dataclass
class Notification:
    id: str
    kind: str
    severity: str  # critical / warn / info
    title: str
    detail: str
    ref_collection: str | None
    ref_id: str | None
    created_at: str
    read: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RefreshSummary:
    run_id: str
    started_at: str
    completed_at: str
    new_count: int
    total_count: int
    by_kind: dict[str, int]


# ─── Builders ───────────────────────────────────────────────────────────────


def _from_audit() -> list[Notification]:
    repo = get_repository()
    reports = sorted(
        repo.list("audit_reports"),
        key=lambda r: r.get("started_at", ""),
        reverse=True,
    )
    if not reports:
        return []
    latest = reports[0]
    out: list[Notification] = []
    for f in latest.get("findings", []) or []:
        sev = f.get("severity")
        if sev not in ("critical", "warn"):
            continue
        nid = f"notif-audit-{latest.get('report_id')}-{f.get('kind')}-{f.get('ref_id') or 'na'}"
        out.append(Notification(
            id=nid,
            kind=f"AUDIT_{sev.upper()}",
            severity=sev,
            title=f.get("title", "(audit finding)"),
            detail=f.get("detail", ""),
            ref_collection=f.get("ref_collection"),
            ref_id=f.get("ref_id"),
            created_at=latest.get("started_at", datetime.now(timezone.utc).isoformat()),
        ))
    return out


def _from_lifecycle_transitions() -> list[Notification]:
    repo = get_repository()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    out: list[Notification] = []
    for t in repo.list("lifecycle_transitions"):
        if (t.get("transitioned_at") or "") < cutoff:
            continue
        nid = f"notif-trans-{t.get('id') or t.get('sub_cap_id')}"
        out.append(Notification(
            id=nid,
            kind="LIFECYCLE_TRANSITION",
            severity="info",
            title=f"{t.get('sub_cap_id')}: {t.get('from_state')} → {t.get('to_state')}",
            detail=f"Score {t.get('score', 0):.0f}",
            ref_collection="lifecycle_scores",
            ref_id=t.get("sub_cap_id"),
            created_at=t.get("transitioned_at", ""),
            metadata={"from_state": t.get("from_state"), "to_state": t.get("to_state")},
        ))
    return out


def _from_suggestions() -> list[Notification]:
    repo = get_repository()
    out: list[Notification] = []
    for s in repo.list("suggestions"):
        if s.get("status") != "pending":
            continue
        nid = f"notif-sug-{s.get('id')}"
        out.append(Notification(
            id=nid,
            kind="SUGGESTION_PENDING",
            severity="info",
            title=f"Pending suggestion: {s.get('title') or s.get('kind')}",
            detail=f"Target {s.get('target')}; gate verdict {s.get('gate_overall')}.",
            ref_collection="suggestions",
            ref_id=s.get("id"),
            created_at=s.get("created_at", ""),
        ))
    return out


# ─── Public API ─────────────────────────────────────────────────────────────


def refresh() -> RefreshSummary:
    repo = get_repository()
    started = datetime.now(timezone.utc)

    candidates = _from_audit() + _from_lifecycle_transitions() + _from_suggestions()
    existing = {n["id"]: n for n in repo.list(NOTIFICATIONS_COLLECTION)}

    new_count = 0
    by_kind: Counter[str] = Counter()
    with repo.defer_persist():
        for n in candidates:
            if n.id in existing:
                # Preserve `read` flag across refresh
                merged = {**asdict(n), "read": existing[n.id].get("read", False)}
            else:
                merged = asdict(n)
                new_count += 1
            repo.upsert(NOTIFICATIONS_COLLECTION, n.id, merged)
            by_kind[n.kind] += 1

    completed = datetime.now(timezone.utc)
    run_id = f"notif-refresh-{int(started.timestamp() * 1_000_000)}"
    summary = RefreshSummary(
        run_id=run_id,
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        new_count=new_count,
        total_count=len(candidates),
        by_kind=dict(by_kind),
    )
    repo.upsert(RUN_COLLECTION, run_id, asdict(summary))
    return summary


def list_notifications(
    *,
    severity: str | None = None,
    unread_only: bool = False,
    limit: int = 200,
) -> list[dict]:
    items = list(get_repository().list(NOTIFICATIONS_COLLECTION))
    if severity:
        items = [n for n in items if n.get("severity") == severity]
    if unread_only:
        items = [n for n in items if not n.get("read")]
    sev_rank = {"critical": 0, "warn": 1, "info": 2}
    items.sort(key=lambda n: (sev_rank.get(n.get("severity", "info"), 3), -_ts(n.get("created_at"))))
    return items[:limit]


def mark_read(notification_id: str) -> dict | None:
    repo = get_repository()
    rec = repo.get(NOTIFICATIONS_COLLECTION, notification_id)
    if not rec:
        return None
    rec = {**rec, "read": True}
    repo.upsert(NOTIFICATIONS_COLLECTION, notification_id, rec)
    return rec


def mark_all_read() -> int:
    repo = get_repository()
    n = 0
    with repo.defer_persist():
        for rec in repo.list(NOTIFICATIONS_COLLECTION):
            if not rec.get("read"):
                repo.upsert(NOTIFICATIONS_COLLECTION, rec["id"], {**rec, "read": True})
                n += 1
    return n


def stats() -> dict[str, Any]:
    items = get_repository().list(NOTIFICATIONS_COLLECTION)
    out: dict[str, int] = {"total": len(items), "unread": 0, "critical": 0, "warn": 0, "info": 0}
    for n in items:
        if not n.get("read"):
            out["unread"] += 1
        out[n.get("severity", "info")] = out.get(n.get("severity", "info"), 0) + 1
    return out


def _ts(iso: str | None) -> float:
    if not iso:
        return 0.0
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0
