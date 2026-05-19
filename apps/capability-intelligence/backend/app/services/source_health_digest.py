"""IMP-13 — daily source-health digest.

The external ingest workers fetch ~35 canonical sources (regulators, vendor
blogs, news feeds). Outages aren't fatal at the per-fetch level — circuit
breakers in :mod:`app.services.source_policy` absorb transient failures —
but a feed that has been silent for 7 days, a vendor portal that's bouncing
on cert errors, or a regulator that flipped ``tos_status`` to ``disabled``
all need operator visibility before they erode coverage.

This module:

1. Records per-source fetch outcomes into the ``source_health_events``
   collection — called by every ingest worker via :func:`record_event`.
2. Aggregates a per-day digest (:func:`compose_digest`) that the daily
   08:00 UTC scheduler renders to plain text (:func:`render_text`) and
   ships via an injected sender. The default sender writes to the
   ``source_health_digests`` collection so the UI can surface the latest
   run; production wires it through to Cloud SMTP / email transport.

No live SMTP credentials are touched here — the sender callable is the
only seam where transport plugs in. Tests use the default repository-only
sender.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from . import source_policy
from .repository import get_repository

logger = logging.getLogger(__name__)

EVENTS_COLLECTION = "source_health_events"
DIGESTS_COLLECTION = "source_health_digests"

STALE_THRESHOLD_DAYS = 7
FAILURE_RATE_THRESHOLD = 0.25


# ─── Events ─────────────────────────────────────────────────────────────────


@dataclass
class SourceEvent:
    event_id: str
    source_id: str
    outcome: str  # success | failure | disabled | circuit_open
    status_code: int | None = None
    error: str | None = None
    duration_ms: int | None = None
    fetched_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version_: str = "source-health-event-v1"


@dataclass
class SourceSummary:
    source_id: str
    success: int = 0
    failure: int = 0
    disabled: int = 0
    circuit_open: int = 0
    last_success_at: str | None = None
    last_failure_at: str | None = None
    last_event_at: str | None = None

    @property
    def total(self) -> int:
        return self.success + self.failure + self.disabled + self.circuit_open

    @property
    def failure_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.failure + self.circuit_open) / self.total


@dataclass
class DigestRow:
    source_id: str
    independence_class: str
    tos_status: str
    success: int
    failure: int
    disabled: int
    circuit_open: int
    failure_rate: float
    last_success_at: str | None
    last_failure_at: str | None
    days_since_success: float | None
    flags: list[str]


@dataclass
class Digest:
    digest_id: str
    window_start: str
    window_end: str
    n_sources_seen: int
    n_flagged: int
    by_flag: dict[str, int]
    rows: list[DigestRow]
    generated_at: str = ""


# ─── Recording ──────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_event(
    source_id: str,
    outcome: str,
    *,
    status_code: int | None = None,
    error: str | None = None,
    duration_ms: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> SourceEvent:
    """Persist a single ingest outcome.

    Called by every external fetcher. ``outcome`` is one of
    ``success`` / ``failure`` / ``disabled`` / ``circuit_open``.
    """
    if outcome not in {"success", "failure", "disabled", "circuit_open"}:
        raise ValueError(f"unknown outcome: {outcome}")
    now = _now_iso()
    event = SourceEvent(
        event_id=f"shev-{source_id}-{int(datetime.now(timezone.utc).timestamp() * 1_000_000)}",
        source_id=source_id,
        outcome=outcome,
        status_code=status_code,
        error=(error or "")[:500] or None,
        duration_ms=duration_ms,
        fetched_at=now,
        metadata=metadata or {},
    )
    get_repository().upsert(EVENTS_COLLECTION, event.event_id, asdict(event))
    return event


# ─── Aggregation ────────────────────────────────────────────────────────────


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _events_in_window(window_start: datetime) -> list[dict[str, Any]]:
    repo = get_repository()
    items = list(repo.list(EVENTS_COLLECTION))
    out = []
    for ev in items:
        ts = _parse_iso(ev.get("fetched_at"))
        if ts is None or ts >= window_start:
            out.append(ev)
    return out


def _summaries_for(events: list[dict[str, Any]]) -> dict[str, SourceSummary]:
    by_source: dict[str, SourceSummary] = {}
    for ev in events:
        sid = ev.get("source_id")
        if not sid:
            continue
        s = by_source.setdefault(sid, SourceSummary(source_id=sid))
        outcome = ev.get("outcome")
        if outcome == "success":
            s.success += 1
        elif outcome == "failure":
            s.failure += 1
        elif outcome == "disabled":
            s.disabled += 1
        elif outcome == "circuit_open":
            s.circuit_open += 1
        ts = ev.get("fetched_at")
        if outcome == "success":
            if not s.last_success_at or ts > s.last_success_at:
                s.last_success_at = ts
        elif outcome in {"failure", "circuit_open"}:
            if not s.last_failure_at or ts > s.last_failure_at:
                s.last_failure_at = ts
        if not s.last_event_at or (ts and ts > s.last_event_at):
            s.last_event_at = ts
    return by_source


def _flags_for(summary: SourceSummary, policy: dict[str, Any], now: datetime) -> list[str]:
    flags: list[str] = []
    if policy.get("tos_status") == "disabled":
        flags.append("disabled")
    if summary.circuit_open > 0:
        flags.append("circuit_open")
    if summary.failure_rate >= FAILURE_RATE_THRESHOLD and summary.total >= 4:
        flags.append("high_failure_rate")
    last = _parse_iso(summary.last_success_at)
    if last is None:
        if summary.total > 0:
            flags.append("never_succeeded")
    else:
        if (now - last).days >= STALE_THRESHOLD_DAYS:
            flags.append("stale")
    return flags


def compose_digest(*, window_hours: int = 24, generated_at: datetime | None = None) -> Digest:
    """Aggregate the last ``window_hours`` of source events into a digest."""
    now = generated_at or datetime.now(timezone.utc)
    window_start = now - timedelta(hours=window_hours)
    events = _events_in_window(window_start)
    summaries = _summaries_for(events)

    rows: list[DigestRow] = []
    flag_counter: Counter = Counter()
    for sid, s in sorted(summaries.items()):
        policy = source_policy.policy_for(sid)
        flags = _flags_for(s, policy, now)
        for f in flags:
            flag_counter[f] += 1
        last_success_dt = _parse_iso(s.last_success_at)
        days_since = (
            round((now - last_success_dt).total_seconds() / 86400, 2)
            if last_success_dt
            else None
        )
        rows.append(DigestRow(
            source_id=sid,
            independence_class=policy.get("independence_class", "regulator"),
            tos_status=policy.get("tos_status", "active"),
            success=s.success,
            failure=s.failure,
            disabled=s.disabled,
            circuit_open=s.circuit_open,
            failure_rate=round(s.failure_rate, 3),
            last_success_at=s.last_success_at,
            last_failure_at=s.last_failure_at,
            days_since_success=days_since,
            flags=flags,
        ))

    n_flagged = sum(1 for r in rows if r.flags)
    return Digest(
        digest_id=f"shd-{now.strftime('%Y%m%d')}",
        window_start=window_start.isoformat(),
        window_end=now.isoformat(),
        n_sources_seen=len(rows),
        n_flagged=n_flagged,
        by_flag=dict(flag_counter),
        rows=rows,
        generated_at=now.isoformat(),
    )


# ─── Rendering ──────────────────────────────────────────────────────────────


def render_text(digest: Digest) -> str:
    lines = [
        "Source health digest",
        f"window: {digest.window_start} → {digest.window_end}",
        f"sources seen: {digest.n_sources_seen}  flagged: {digest.n_flagged}",
        "",
    ]
    if digest.by_flag:
        lines.append("Flag counts:")
        for flag, count in sorted(digest.by_flag.items()):
            lines.append(f"  - {flag}: {count}")
        lines.append("")

    if digest.n_flagged == 0:
        lines.append("No flagged sources. All good.")
        return "\n".join(lines)

    lines.append("Flagged sources:")
    for row in digest.rows:
        if not row.flags:
            continue
        flags = ", ".join(row.flags)
        last = row.last_success_at or "never"
        lines.append(
            f"  - {row.source_id} [{row.independence_class}] flags={flags} "
            f"successes={row.success} failures={row.failure} "
            f"last_success_at={last}"
        )
    return "\n".join(lines)


# ─── Sending ────────────────────────────────────────────────────────────────


Sender = Callable[[Digest, str], dict[str, Any]]


def _repo_sender(digest: Digest, body: str) -> dict[str, Any]:
    """Default sender — persist the rendered digest so the UI can show it."""
    payload = {
        "digest_id": digest.digest_id,
        "generated_at": digest.generated_at,
        "window_start": digest.window_start,
        "window_end": digest.window_end,
        "n_sources_seen": digest.n_sources_seen,
        "n_flagged": digest.n_flagged,
        "by_flag": digest.by_flag,
        "body": body,
        "transport": "repository",
    }
    get_repository().upsert(DIGESTS_COLLECTION, digest.digest_id, payload)
    return payload


def send_digest(
    *,
    window_hours: int = 24,
    sender: Sender | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Compose + render + dispatch the daily digest.

    The default ``sender`` writes to the ``source_health_digests``
    repository collection so the digest is always discoverable in
    Mission Control even when no email transport is wired.
    """
    digest = compose_digest(window_hours=window_hours, generated_at=generated_at)
    body = render_text(digest)
    sender = sender or _repo_sender
    return sender(digest, body)


def list_recent_digests(limit: int = 30) -> list[dict[str, Any]]:
    items = list(get_repository().list(DIGESTS_COLLECTION))
    items.sort(key=lambda r: r.get("generated_at", ""), reverse=True)
    return items[:limit]
