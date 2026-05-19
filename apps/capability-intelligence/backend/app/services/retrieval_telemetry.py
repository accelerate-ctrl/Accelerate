"""RAG retrieval telemetry (IMP-8).

Implementation Steps §3 IMP-8: today's RAG retriever is a black box.
When chat gives a wrong answer, we can't tell whether retrieval pulled
bad chunks or whether the LLM mis-synthesised the right ones. This
service records per-query telemetry so the QA dashboard surfaces
``retrieval hits by index`` + ``structured filter rate`` + recent
queries with their top-K scores.

The :func:`record` helper is meant to be invoked from
:mod:`rag.hybrid_retriever` immediately after each query — it accepts
a list of :class:`RetrievalHit`-style entries and the originating
query string + operation. The persisted shape mirrors what the QA
Dashboard tile renders.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .repository import get_repository

logger = logging.getLogger(__name__)

TELEMETRY_COLLECTION = "retrieval_telemetry"


@dataclass
class RetrievalEvent:
    """One persisted retrieval event."""

    event_id: str
    query: str
    operation: str  # ``chat`` / ``deep_dive`` / ``digest`` / …
    user_email: str | None
    sub_cap_id: str | None  # extracted exact id, if any
    structured_filter_hit: bool
    k_returned: int
    by_signal: dict[str, int]  # how many candidates each signal contributed
    by_kind: dict[str, int]   # subcap / maturity / story / l4_feature / theme / persona
    top_doc_ids: list[str]
    top_score: float
    fusion_score_mean: float
    recorded_at: str = ""
    schema_version_: str = "retrieval-event-v1"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["_schema_version"] = d.pop("schema_version_")
        return d


# ─── Public API ───────────────────────────────────────────────────────────


def record(
    *,
    query: str,
    operation: str,
    hits: list[Any],
    user_email: str | None = None,
    sub_cap_id: str | None = None,
) -> RetrievalEvent:
    """Persist a telemetry event for one retrieval call.

    Accepts the hits list directly (each hit must expose ``doc_id``,
    ``metadata`` dict, ``score`` float, and ``signals`` list). Tolerates
    missing fields so a misbehaving caller can't crash the LLM path.
    """
    by_signal: Counter[str] = Counter()
    by_kind: Counter[str] = Counter()
    structured_hit = False
    top_doc_ids: list[str] = []
    scores: list[float] = []
    for hit in hits or []:
        # Handle both dataclass and dict shapes.
        meta = getattr(hit, "metadata", None) or {}
        if not isinstance(meta, dict):
            meta = dict(meta)
        signals = getattr(hit, "signals", None) or []
        if not isinstance(signals, list):
            signals = list(signals)
        for s in signals:
            by_signal[str(s)] += 1
            if s == "structured":
                structured_hit = True
        kind = meta.get("kind") or "unknown"
        by_kind[str(kind)] += 1
        doc_id = getattr(hit, "doc_id", None) or meta.get("source_id")
        if doc_id and len(top_doc_ids) < 5:
            top_doc_ids.append(str(doc_id))
        score = getattr(hit, "score", None)
        if isinstance(score, (int, float)):
            scores.append(float(score))

    top_score = max(scores) if scores else 0.0
    fusion_mean = (sum(scores) / len(scores)) if scores else 0.0

    event = RetrievalEvent(
        event_id=f"retrieval-{int(datetime.now(timezone.utc).timestamp() * 1_000)}-{uuid4().hex[:6]}",
        query=(query or "")[:500],
        operation=operation,
        user_email=(user_email or "").lower() or None,
        sub_cap_id=sub_cap_id,
        structured_filter_hit=structured_hit,
        k_returned=len(hits or []),
        by_signal=dict(by_signal),
        by_kind=dict(by_kind),
        top_doc_ids=top_doc_ids,
        top_score=round(top_score, 6),
        fusion_score_mean=round(fusion_mean, 6),
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    try:
        get_repository().upsert(TELEMETRY_COLLECTION, event.event_id, event.to_dict())
    except Exception:
        logger.exception("failed to persist retrieval telemetry; query=%s", query[:60])
    return event


def list_recent(*, limit: int = 100, operation: str | None = None) -> list[dict]:
    rows = get_repository().list(TELEMETRY_COLLECTION)
    if operation:
        rows = [r for r in rows if r.get("operation") == operation]
    rows.sort(key=lambda r: r.get("recorded_at") or "", reverse=True)
    return rows[:limit]


def summary(*, since: str | None = None) -> dict[str, Any]:
    """Aggregated tile for the QA dashboard.

    Returns:
      - ``hits_by_signal``: total candidate count per signal across
        all recorded events.
      - ``hits_by_kind``: same per chunk kind.
      - ``structured_filter_rate``: fraction of queries that resolved
        an exact identifier.
      - ``zero_hit_queries``: queries that returned no hits at all —
        these are the actionable ones for retrieval debugging.
      - ``avg_top_score`` + ``avg_k_returned``: overall health.
    """
    rows = list(get_repository().list(TELEMETRY_COLLECTION))
    if since:
        rows = [r for r in rows if (r.get("recorded_at") or "") >= since]
    if not rows:
        return {
            "events": 0,
            "hits_by_signal": {},
            "hits_by_kind": {},
            "structured_filter_rate": 0.0,
            "zero_hit_queries": [],
            "avg_top_score": 0.0,
            "avg_k_returned": 0.0,
        }
    sig: Counter[str] = Counter()
    kind: Counter[str] = Counter()
    structured = 0
    zero_hit: list[str] = []
    top_scores: list[float] = []
    ks: list[int] = []
    for r in rows:
        for s, n in (r.get("by_signal") or {}).items():
            sig[s] += int(n or 0)
        for k_, n in (r.get("by_kind") or {}).items():
            kind[k_] += int(n or 0)
        if r.get("structured_filter_hit"):
            structured += 1
        if int(r.get("k_returned") or 0) == 0:
            zero_hit.append(str(r.get("query") or ""))
        top_scores.append(float(r.get("top_score") or 0.0))
        ks.append(int(r.get("k_returned") or 0))
    n = len(rows)
    return {
        "events": n,
        "hits_by_signal": dict(sig),
        "hits_by_kind": dict(kind),
        "structured_filter_rate": round(structured / n, 4),
        "zero_hit_queries": zero_hit[:20],
        "avg_top_score": round(sum(top_scores) / n, 6),
        "avg_k_returned": round(sum(ks) / n, 2),
    }


__all__ = [
    "RetrievalEvent",
    "TELEMETRY_COLLECTION",
    "list_recent",
    "record",
    "summary",
]
