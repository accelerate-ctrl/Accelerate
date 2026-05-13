"""Trends synthesis — cluster news items by semantic similarity.

Groups recent news_items into trend clusters using the 256-d hash
embeddings (``llm.embeddings.embed_text``) and a deterministic K-Means
(``cluster_service._kmeans``). Each cluster is summarised by Gemini Flash
(one cheap call per cluster, not per item) into:

    {
      cluster_id,        # stable hash of the sorted member ids
      label,             # ≤6-word title from the LLM
      summary,           # one-sentence implication for the catalogue
      count,             # member item count
      top_sources,       # most frequent source domains
      time_series,       # week-bucketed counts for sparkline
      member_ids,        # news_item ids
      first_seen / last_seen
    }

A daily Cloud Run Job (``backend/app/jobs/trends_recompute.py``)
re-runs this; the rest of the app reads from the
``trend_clusters`` collection.
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .llm.embeddings import embed_text
from .repository import get_repository

log = logging.getLogger(__name__)

NEWS_COLLECTION = "news_items"
TRENDS_COLLECTION = "trend_clusters"

DEFAULT_K = 8                  # target number of trend clusters
DEFAULT_LOOKBACK_DAYS = 30     # how far back to pull news items
MIN_MEMBERS_PER_CLUSTER = 2    # drop singletons


def _doc_text(item: dict) -> str:
    """Build the text we embed for similarity."""
    bits = [
        item.get("title") or "",
        item.get("summary") or "",
        (item.get("text") or "")[:400],
    ]
    return " ".join(b for b in bits if b).strip()


def _domain(url: str | None) -> str:
    if not url:
        return ""
    url = str(url)
    try:
        from urllib.parse import urlparse
        return (urlparse(url).netloc or "").replace("www.", "")
    except Exception:  # noqa: BLE001
        return ""


def _week_key(iso: str | None) -> str:
    if not iso:
        return "0000-W00"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return "0000-W00"
    iso_y, iso_w, _ = dt.isocalendar()
    return f"{iso_y:04d}-W{iso_w:02d}"


def _cluster_id(member_ids: list[str]) -> str:
    """Stable id derived from the sorted member set."""
    h = hashlib.sha256("|".join(sorted(member_ids)).encode()).hexdigest()[:10]
    return f"trend-{h}"


def _summarise_cluster(items: list[dict]) -> dict:
    """Cheap Gemini-Flash call to label + describe the cluster."""
    from .llm.router import LlmRequest, ModelKind
    from .llm.router import call as llm_call

    head = items[:6]
    titles = "\n".join(f"- {(i.get('title') or '')[:160]}" for i in head)
    sources = ", ".join({(_domain(i.get("url")) or i.get("source") or "?") for i in head})
    prompt = (
        "You are summarising a cluster of recent FS-industry news items.\n"
        "Return JSON: {\"label\": \"≤6 words\", \"summary\": \"one sentence on "
        "catalogue implication\"}\n\n"
        f"Top {len(head)} headlines:\n{titles}\n"
        f"Sources: {sources}\n"
    )
    try:
        resp = llm_call(LlmRequest(
            model=ModelKind.GEMINI_FLASH,
            prompt=prompt,
            system="Output strict JSON only. Be precise and conservative.",
            max_tokens=200,
            metadata={"operation_type": "trends_cluster_summary"},
        ))
        from .news_service import _ensure_dict
        payload = _ensure_dict(resp.text)
    except Exception as exc:  # noqa: BLE001
        log.warning("trends cluster summary failed: %s", exc)
        payload = {}
    return {
        "label": (payload.get("label") or "Unlabelled cluster")[:80],
        "summary": (payload.get("summary") or "")[:400],
    }


def recompute_clusters(*, k: int = DEFAULT_K,
                       lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> dict:
    """Pull recent news items, embed, K-Means, summarise each cluster,
    persist to `trend_clusters`. Returns a run summary."""
    from .cluster_service import _kmeans

    repo = get_repository()
    started = datetime.now(timezone.utc)
    cutoff = started.timestamp() - lookback_days * 86_400

    items: list[dict] = []
    for it in repo.list(NEWS_COLLECTION):
        pub = it.get("published_at") or ""
        try:
            ts = datetime.fromisoformat(pub.replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            continue
        if ts >= cutoff:
            items.append(it)

    if len(items) < 2 * MIN_MEMBERS_PER_CLUSTER:
        log.info("trends_recompute: only %d items in window — clearing", len(items))
        # Replace collection with empty list rather than leaving stale clusters
        for stale in repo.list(TRENDS_COLLECTION):
            repo.delete(TRENDS_COLLECTION, stale.get("cluster_id") or stale.get("id"))
        return {
            "started_at": started.isoformat(),
            "items_considered": len(items),
            "clusters_written": 0,
        }

    # Embed every item.
    embeds = [embed_text(_doc_text(it)) for it in items]
    actual_k = max(2, min(k, len(items) // MIN_MEMBERS_PER_CLUSTER))

    # _kmeans takes [(id, vec), ...] → {label: [(id, vec), ...]}.
    points = [(items[i].get("id") or items[i].get("news_id") or str(i), embeds[i])
              for i in range(len(items))]
    grouped = _kmeans(points, k=actual_k, max_iter=40, seed=42)

    # Build {item_id: group_label}
    by_cluster: dict[int, list[int]] = {}
    id_to_index = {points[i][0]: i for i in range(len(points))}
    for lab, pts in grouped.items():
        for pid, _vec in pts:
            i = id_to_index.get(pid)
            if i is not None:
                by_cluster.setdefault(int(lab), []).append(i)

    written = 0
    cluster_ids_written: set[str] = set()
    for _lab, idxs in by_cluster.items():
        if len(idxs) < MIN_MEMBERS_PER_CLUSTER:
            continue
        members = [items[i] for i in idxs]
        member_ids = [m.get("id") or m.get("news_id") or "" for m in members if m.get("id") or m.get("news_id")]
        if not member_ids:
            continue
        cid = _cluster_id(member_ids)
        cluster_ids_written.add(cid)

        # Time-series bucketed by ISO week.
        weeks = Counter(_week_key(m.get("published_at")) for m in members)
        time_series = [{"week": w, "count": c} for w, c in sorted(weeks.items())]

        # Source mix.
        srcs = Counter(_domain(m.get("url")) or (m.get("source") or "") for m in members)
        top_sources = [{"source": s, "count": c} for s, c in srcs.most_common(5) if s]

        # Aggregate downstream impact signals if present.
        impact_classes = Counter(
            ((m.get("impact") or {}).get("impact_class") or "no_impact")
            for m in members
        )

        meta = _summarise_cluster(members)
        published = [m.get("published_at") for m in members if m.get("published_at")]
        published.sort()
        record: dict[str, Any] = {
            "cluster_id": cid,
            "label": meta["label"],
            "summary": meta["summary"],
            "count": len(member_ids),
            "member_ids": member_ids,
            "top_sources": top_sources,
            "time_series": time_series,
            "impact_class_mix": dict(impact_classes),
            "first_seen": published[0] if published else None,
            "last_seen": published[-1] if published else None,
            "computed_at": started.isoformat(),
        }
        repo.upsert(TRENDS_COLLECTION, cid, record)
        written += 1

    # Prune clusters not in the current run (stale).
    for stale in repo.list(TRENDS_COLLECTION):
        sid = stale.get("cluster_id") or stale.get("id")
        if sid and sid not in cluster_ids_written:
            repo.delete(TRENDS_COLLECTION, sid)

    return {
        "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "items_considered": len(items),
        "clusters_written": written,
        "k_requested": k,
        "k_used": actual_k,
        "lookback_days": lookback_days,
    }


def list_clusters(*, limit: int = 50) -> list[dict]:
    rows = list(get_repository().list(TRENDS_COLLECTION))
    rows.sort(key=lambda r: (r.get("last_seen") or "", r.get("count") or 0), reverse=True)
    return rows[:limit]


def get_cluster(cluster_id: str) -> dict | None:
    return get_repository().get(TRENDS_COLLECTION, cluster_id)
