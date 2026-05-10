"""Claim-label promotion / demotion handler.

Per QA_AUDIT.md fix #18. The KG carries ``claim_label`` on edges
(FACT / INFERENCE / HYPOTHESIS / CEILING_ESTIMATE). Promotion is what
elevates a HYPOTHESIS to INFERENCE when 2+ corroborating sources land;
demotion is what reverses that when a corroborating source retracts.

This module:
    - records the per-edge promotion / demotion event
    - provides the ``on_source_retraction(source_id)`` handler that
      sweeps edges for affected claims and demotes them
    - exposes ``recompute_label_for_edge(edge_id)`` for diagnostic use
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..models.common import ClaimLabel
from .repository import get_repository

logger = logging.getLogger(__name__)

EDGE_COLLECTION = "graph_edges"
PROMOTION_EVENTS_COLLECTION = "claim_promotions"


def _label_for_evidence(source_count: int, top_tier: str | None) -> str:
    """Per spec §8 promotion rules — simplified.

    Tiers: T1 ≥ 2 → FACT
            T1 + T2 ≥ 1 each, or T2 ≥ 2 → INFERENCE
            anything else → HYPOTHESIS
    """
    if source_count >= 2 and top_tier == "T1":
        return ClaimLabel.FACT.value
    if source_count >= 2:
        return ClaimLabel.INFERENCE.value
    if source_count == 1:
        return ClaimLabel.HYPOTHESIS.value
    return ClaimLabel.CEILING_ESTIMATE.value


def recompute_label_for_edge(edge_id: str, *, exclude_source: str | None = None) -> str:
    """Recompute a single edge's claim_label given current sources."""
    repo = get_repository()
    edge = repo.get(EDGE_COLLECTION, edge_id)
    if not edge:
        raise KeyError(edge_id)
    sources = [s for s in (edge.get("sources") or []) if s.get("id") != exclude_source]
    top_tier = min((s.get("tier", "T5") for s in sources), default="T5")
    return _label_for_evidence(len(sources), top_tier)


def on_source_retraction(source_id: str) -> dict[str, Any]:
    """Sweep every edge that cites ``source_id``; demote when warranted.

    Emits a ``claim_promotions`` row for each demotion (or no-op result)
    so the audit trail captures the cascade.
    """
    repo = get_repository()
    affected_edges = [
        e for e in repo.list(EDGE_COLLECTION)
        if any(s.get("id") == source_id for s in e.get("sources") or [])
    ]
    n_demoted = 0
    now = datetime.now(timezone.utc).isoformat()
    with repo.defer_persist():
        for e in affected_edges:
            old_label = e.get("claim_label")
            new_label = recompute_label_for_edge(e["id"], exclude_source=source_id)
            if old_label != new_label:
                e_updated = {**e, "claim_label": new_label, "demoted_at": now}
                e_updated["sources"] = [s for s in e.get("sources") or [] if s.get("id") != source_id]
                repo.upsert(EDGE_COLLECTION, e["id"], e_updated)
                evt_id = f"demote-{e['id']}-{int(datetime.now(timezone.utc).timestamp() * 1_000_000)}"
                repo.upsert(
                    PROMOTION_EVENTS_COLLECTION,
                    evt_id,
                    {
                        "id": evt_id,
                        "edge_id": e["id"],
                        "kind": "demotion",
                        "from_label": old_label,
                        "to_label": new_label,
                        "trigger": "source_retraction",
                        "trigger_source_id": source_id,
                        "at": now,
                    },
                )
                n_demoted += 1
    return {
        "retracted_source_id": source_id,
        "edges_affected": len(affected_edges),
        "edges_demoted": n_demoted,
        "at": now,
    }


def on_corroborating_source(edge_id: str, new_source: dict) -> dict[str, Any]:
    """Add a new source to an edge; promote claim_label when threshold hits."""
    repo = get_repository()
    edge = repo.get(EDGE_COLLECTION, edge_id)
    if not edge:
        raise KeyError(edge_id)
    old_label = edge.get("claim_label")
    sources = (edge.get("sources") or []) + [new_source]
    top_tier = min((s.get("tier", "T5") for s in sources), default="T5")
    new_label = _label_for_evidence(len(sources), top_tier)
    now = datetime.now(timezone.utc).isoformat()
    repo.upsert(
        EDGE_COLLECTION,
        edge_id,
        {**edge, "sources": sources, "claim_label": new_label, "promoted_at": now},
    )
    if old_label != new_label:
        evt_id = f"promote-{edge_id}-{int(datetime.now(timezone.utc).timestamp() * 1_000_000)}"
        repo.upsert(
            PROMOTION_EVENTS_COLLECTION,
            evt_id,
            {
                "id": evt_id,
                "edge_id": edge_id,
                "kind": "promotion",
                "from_label": old_label,
                "to_label": new_label,
                "trigger": "corroborating_source",
                "trigger_source_id": new_source.get("id"),
                "at": now,
            },
        )
    return {
        "edge_id": edge_id,
        "from_label": old_label,
        "to_label": new_label,
        "n_sources": len(sources),
    }
