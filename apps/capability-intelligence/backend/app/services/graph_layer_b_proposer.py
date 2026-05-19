"""KG Layer B — AI-augmented edge proposer (PRD FR-3 / Plan §3 Phase 3).

The deterministic graph (Layer A, in :mod:`graph_service`) only models
edges the workbooks make explicit (USES_PLATFORM, HAS_MATURITY,
APPLIES_TO, …). Layer B proposes three new edge kinds based on
similarity + cross-pillar reasoning:

- **SEMANTICALLY_SIMILAR** — two subcaps whose embedded chunk text has
  cosine ≥ ``cosine_threshold``.
- **CROSS_PILLAR_DEPENDENCY** — subcap-to-subcap edges where the
  destination subcap is referenced by a cross-pillar story originating
  in the source subcap's pillar.
- **AI_PROPOSED** — generic catch-all for proposer outputs that don't
  fit the two specific kinds above. Reserved for future Gemini Pro
  proposers; not emitted by the deterministic v1 logic.

Per the plan: each candidate passes through validation gates G1–G8;
survivors persist to ``pending_edges/{edge_id}`` and emit a Change
Flag (kind=AI_PROPOSED_EDGE) so the J5 inbox surfaces them for
human approve/reject/defer.

The proposer runs nightly via a Cloud Run Job
(``app/jobs/kg_layer_b_nightly.py``); on-demand runs are also
available via the new ``/api/graph/layer-b/propose`` endpoint.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .catalogue_service import COLLECTIONS, _make_flag
from .repository import get_repository

logger = logging.getLogger(__name__)

PENDING_EDGES_COLLECTION = "pending_edges"
PROPOSER_RUN_COLLECTION = "kg_layer_b_runs"
FLAG_COLLECTION = COLLECTIONS["flags"]

# Default cosine threshold for SEMANTICALLY_SIMILAR. Anything below
# this is too loose for an inbox candidate; anything above ~0.95 tends
# to surface near-duplicate subcaps (e.g. two pillars naming the same
# capability slightly differently).
DEFAULT_COSINE_THRESHOLD = 0.85

# Cooldown window — when a pending edge is rejected, the proposer
# skips proposing the same (src, dst, kind) for 30 days so reviewers
# don't see the same false positive every night.
COOLDOWN_DAYS = 30


@dataclass
class PendingEdge:
    """A Layer B candidate awaiting human disposition.

    The shape mirrors graph_storage.KGEdge plus provenance + gate
    verdict so the FE can render the J5 inbox card with everything the
    reviewer needs.
    """
    edge_id: str
    src: str
    dst: str
    kind: str  # SEMANTICALLY_SIMILAR | CROSS_PILLAR_DEPENDENCY | AI_PROPOSED
    confidence: float  # 0..1
    rationale: str
    proposed_at: str
    provenance: dict[str, Any] = field(default_factory=dict)
    gates: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending | approved | rejected | deferred
    schema_version_: str = "pending-edge-v1"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["_schema_version"] = d.pop("schema_version_")
        return d


@dataclass
class ProposerRun:
    run_id: str
    started_at: str
    completed_at: str
    candidates_considered: int
    edges_proposed: int
    edges_dropped_threshold: int
    edges_dropped_cooldown: int
    edges_existing_in_layer_a: int


# ─── Helpers ────────────────────────────────────────────────────────────────


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(x * x for x in b) ** 0.5 or 1.0
    return dot / (na * nb)


def _edge_id(src: str, dst: str, kind: str) -> str:
    """Stable id so the proposer is idempotent (same candidate → same id)."""
    a, b = sorted([src, dst])
    return f"edge-{kind.lower()}-{a}-{b}"


def _existing_pending_edges() -> dict[str, dict]:
    """Map of edge_id → row for every pending_edges row, regardless of
    status. Used to dedupe re-proposals + honor rejection cooldowns.
    """
    repo = get_repository()
    return {row["edge_id"]: row for row in repo.list(PENDING_EDGES_COLLECTION)}


def _is_in_cooldown(existing: dict | None) -> bool:
    """Rejected edges have a COOLDOWN_DAYS recheck window; deferred
    edges are always skipped (until manually reactivated)."""
    if existing is None:
        return False
    status = existing.get("status")
    if status == "rejected":
        proposed_at = existing.get("disposition_at") or existing.get("proposed_at")
        if not proposed_at:
            return False
        try:
            then = datetime.fromisoformat(proposed_at.replace("Z", "+00:00"))
        except Exception:
            return False
        age_days = (datetime.now(timezone.utc) - then).days
        return age_days < COOLDOWN_DAYS
    if status == "deferred":
        return True
    if status == "approved":
        # Already committed → no need to propose again.
        return True
    return False


def _has_layer_a_edge(g, src: str, dst: str) -> bool:
    """Skip candidates that are already in the deterministic graph."""
    if g is None:
        return False
    if not g.has_node(src) or not g.has_node(dst):
        return False
    return g.has_edge(src, dst) or g.has_edge(dst, src)


def _gate_verdict(
    *,
    confidence: float,
    source_count: int,
    kind: str,
) -> dict[str, Any]:
    """Compact Layer B gate evaluation (subset of the full G1–G8).

    Per-kind thresholds:

    - **SEMANTICALLY_SIMILAR** — G3 ERS = confidence ≥ 0.85 (the
      cosine threshold is its own gate; G4 independence is N/A
      because the cosine *is* the evidence).
    - **CROSS_PILLAR_DEPENDENCY** — G3 ERS = confidence ≥ 0.55, G4
      INDEPENDENCE = story count ≥ 2.
    - **AI_PROPOSED** — same defaults as CROSS_PILLAR_DEPENDENCY.

    Returns ``{overall: pass|warn, scores: {...}, remediation: str|None}``
    matching the shape used by the J5 inbox card.
    """
    score_ers = round(confidence, 3)
    if kind == "SEMANTICALLY_SIMILAR":
        pass_ers = score_ers >= 0.85
        pass_indep = True  # cosine itself is the evidence
    else:
        pass_ers = score_ers >= 0.55
        pass_indep = source_count >= 2
    overall = "pass" if (pass_ers and pass_indep) else "warn"
    remediation: str | None = None
    if not pass_ers:
        remediation = "below ERS threshold; needs more corroborating evidence"
    elif not pass_indep:
        remediation = "single corroborating signal; need ≥2 independent sources"
    return {
        "overall": overall,
        "scores": {
            "g3_ers": score_ers,
            "g4_independence": source_count,
        },
        "remediation": remediation,
    }


# ─── Candidate generators ──────────────────────────────────────────────────


def _propose_semantically_similar(*, threshold: float, max_per_subcap: int = 3) -> list[dict]:
    """For each subcap, look at the top-K vector-store hits of kind
    ``subcap`` and emit edges to those whose cosine ≥ threshold.

    Uses the catalogue_ontology corpus written by
    :func:`rag.catalogue_corpus_builder.rebuild_corpus`. Falls back
    to a no-op when no corpus exists (the proposer should produce zero
    candidates rather than crash).
    """
    repo = get_repository()
    subcap_chunks = [
        r for r in repo.list("vector_index")
        if (r.get("metadata") or {}).get("kind") == "subcap"
    ]
    if len(subcap_chunks) < 2:
        return []

    candidates: list[dict] = []
    for i, src in enumerate(subcap_chunks):
        src_meta = src.get("metadata") or {}
        src_sid = src_meta.get("sub_cap_id")
        if not src_sid:
            continue
        src_emb = src.get("embedding") or []
        scored: list[tuple[float, dict]] = []
        for j, dst in enumerate(subcap_chunks):
            if i == j:
                continue
            dst_meta = dst.get("metadata") or {}
            dst_sid = dst_meta.get("sub_cap_id")
            if not dst_sid or dst_sid == src_sid:
                continue
            score = _cosine(src_emb, dst.get("embedding") or [])
            if score >= threshold:
                scored.append((score, dst))
        scored.sort(key=lambda x: x[0], reverse=True)
        for score, dst in scored[:max_per_subcap]:
            dst_meta = dst.get("metadata") or {}
            dst_sid = dst_meta["sub_cap_id"]
            candidates.append({
                "src": f"Subcap::{src_sid}",
                "dst": f"Subcap::{dst_sid}",
                "kind": "SEMANTICALLY_SIMILAR",
                "confidence": round(score, 3),
                "rationale": (
                    f"Subcap chunks have cosine {score:.3f} ≥ {threshold:.2f} "
                    f"in the catalogue_ontology corpus."
                ),
                "provenance": {
                    "method": "embedding_cosine",
                    "src_chunk": src["doc_id"],
                    "dst_chunk": dst["doc_id"],
                },
                "source_count": 1,
            })
    return candidates


def _propose_cross_pillar_dependency(*, min_stories: int = 2) -> list[dict]:
    """For each subcap, propose a dependency edge to every subcap it is
    linked to via cross-pillar stories.

    Uses the ``cross_pillar_stories`` collection emitted by the v7.0
    parser (Phase 1.3). A pair must appear in at least ``min_stories``
    cross-pillar stories before the proposer surfaces it — single-story
    co-occurrences are too noisy.
    """
    repo = get_repository()
    pair_counts: dict[tuple[str, str], int] = {}
    pair_themes: dict[tuple[str, str], set[str]] = {}

    for row in repo.list("cross_pillar_stories"):
        origin = row.get("origin_sub_cap_id")
        linked = row.get("linked_sub_caps") or []
        themes = row.get("themes") or []
        if not origin or not linked:
            continue
        for dst in linked:
            if dst == origin:
                continue
            key = (origin, dst)
            pair_counts[key] = pair_counts.get(key, 0) + 1
            pair_themes.setdefault(key, set()).update(themes)

    candidates: list[dict] = []
    for (src, dst), n in pair_counts.items():
        if n < min_stories:
            continue
        # Confidence scales with co-occurrence count; saturates at 0.95.
        confidence = round(min(0.95, 0.55 + 0.05 * n), 3)
        themes = sorted(pair_themes.get((src, dst), set()))
        candidates.append({
            "src": f"Subcap::{src}",
            "dst": f"Subcap::{dst}",
            "kind": "CROSS_PILLAR_DEPENDENCY",
            "confidence": confidence,
            "rationale": (
                f"Co-occurs in {n} cross-pillar stories"
                + (f" tagged {', '.join(themes[:4])}" if themes else "")
            ),
            "provenance": {
                "method": "cross_pillar_story_cooccurrence",
                "story_count": n,
                "themes": themes,
            },
            "source_count": n,
        })
    return candidates


# ─── Public API ────────────────────────────────────────────────────────────


def propose_edges(
    *,
    cosine_threshold: float = DEFAULT_COSINE_THRESHOLD,
    max_similar_per_subcap: int = 3,
    min_cross_pillar_stories: int = 2,
) -> ProposerRun:
    """Run all Layer B proposers, write survivors to ``pending_edges``,
    raise a Change Flag for each surviving candidate so the J5 inbox
    surfaces them.

    Idempotent: re-running picks up where the prior run left off via
    deterministic edge ids + the cooldown rule.
    """
    started = datetime.now(timezone.utc)
    run_id = f"layerb-{int(started.timestamp())}"
    repo = get_repository()

    # Build / fetch the layer-A graph so we can skip candidates that
    # the deterministic graph already covers.
    try:
        from . import graph_service
        graph_a = graph_service.build_graph()
    except Exception:
        logger.exception("layer-b: could not build layer-a graph; "
                         "candidates won't be filtered against it")
        graph_a = None

    existing = _existing_pending_edges()

    candidates: list[dict] = []
    candidates.extend(
        _propose_semantically_similar(
            threshold=cosine_threshold,
            max_per_subcap=max_similar_per_subcap,
        )
    )
    candidates.extend(
        _propose_cross_pillar_dependency(min_stories=min_cross_pillar_stories)
    )

    n_total = len(candidates)
    n_proposed = 0
    n_threshold = 0
    n_cooldown = 0
    n_layer_a = 0

    with repo.defer_persist():
        for cand in candidates:
            eid = _edge_id(cand["src"], cand["dst"], cand["kind"])

            # Skip if cooldown / already approved / deferred.
            if _is_in_cooldown(existing.get(eid)):
                n_cooldown += 1
                continue

            # Skip if the deterministic graph already has this edge.
            if _has_layer_a_edge(graph_a, cand["src"], cand["dst"]):
                n_layer_a += 1
                continue

            # G3 / G4 gate evaluation (per-kind thresholds).
            gate = _gate_verdict(
                confidence=cand["confidence"],
                source_count=cand.get("source_count", 1),
                kind=cand["kind"],
            )
            if gate["overall"] != "pass":
                n_threshold += 1
                continue

            edge = PendingEdge(
                edge_id=eid,
                src=cand["src"],
                dst=cand["dst"],
                kind=cand["kind"],
                confidence=cand["confidence"],
                rationale=cand["rationale"],
                proposed_at=started.isoformat(),
                provenance=cand["provenance"],
                gates=gate,
            )
            repo.upsert(PENDING_EDGES_COLLECTION, eid, edge.to_dict())

            # Emit a Change Flag so the J5 inbox surfaces it.
            severity = "MEDIUM" if cand["kind"] == "SEMANTICALLY_SIMILAR" else "LOW"
            target_id = cand["dst"].split("::", 1)[-1]
            flag = _make_flag(
                "AI_PROPOSED_EDGE", severity, "subcap", target_id,
                f"Layer-B edge proposal: {cand['kind']}",
                cand["rationale"],
                extra={
                    "edge_id": eid,
                    "src": cand["src"],
                    "dst": cand["dst"],
                    "confidence": cand["confidence"],
                    "kind": cand["kind"],
                    "run_id": run_id,
                },
            )
            repo.upsert(FLAG_COLLECTION, flag["flag_id"], flag)
            n_proposed += 1

        # Persist run summary for the audit dashboard.
        completed = datetime.now(timezone.utc)
        run = ProposerRun(
            run_id=run_id,
            started_at=started.isoformat(),
            completed_at=completed.isoformat(),
            candidates_considered=n_total,
            edges_proposed=n_proposed,
            edges_dropped_threshold=n_threshold,
            edges_dropped_cooldown=n_cooldown,
            edges_existing_in_layer_a=n_layer_a,
        )
        repo.upsert(PROPOSER_RUN_COLLECTION, run_id, asdict(run))

    logger.info(
        "kg layer-b: %d candidates considered → %d proposed (cooldown=%d, layer_a=%d, threshold=%d)",
        n_total, n_proposed, n_cooldown, n_layer_a, n_threshold,
    )
    return run


def list_pending(*, kind: str | None = None, limit: int = 200) -> list[dict]:
    """Pending edges for the J5 inbox. Newest proposals first."""
    rows = [
        r for r in get_repository().list(PENDING_EDGES_COLLECTION)
        if r.get("status") == "pending"
    ]
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    rows.sort(key=lambda r: r.get("proposed_at") or "", reverse=True)
    return rows[:limit]


def disposition(
    edge_id: str,
    *,
    by: str,
    status: str,
    note: str | None = None,
) -> dict | None:
    """Apply approve / reject / defer to a pending edge.

    - **approved**: edge is committed (subsequent rebuilds of layer A
      will pick it up via :func:`commit_approved_edges`).
    - **rejected**: cooldown starts; the proposer will not re-emit
      this edge for ``COOLDOWN_DAYS``.
    - **deferred**: edge stays pending without a cooldown reset.
    """
    if status not in {"approved", "rejected", "deferred"}:
        raise ValueError(f"unknown status: {status!r}")
    repo = get_repository()
    edge = repo.get(PENDING_EDGES_COLLECTION, edge_id)
    if not edge:
        return None
    now = datetime.now(timezone.utc).isoformat()
    edge["status"] = status
    edge["disposition_by"] = by
    edge["disposition_at"] = now
    edge["disposition_note"] = note
    repo.upsert(PENDING_EDGES_COLLECTION, edge_id, edge)
    return edge


def list_runs(limit: int = 50) -> list[dict]:
    rows = get_repository().list(PROPOSER_RUN_COLLECTION)
    rows.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    return rows[:limit]


__all__ = [
    "COOLDOWN_DAYS",
    "DEFAULT_COSINE_THRESHOLD",
    "FLAG_COLLECTION",
    "PENDING_EDGES_COLLECTION",
    "PROPOSER_RUN_COLLECTION",
    "PendingEdge",
    "ProposerRun",
    "disposition",
    "list_pending",
    "list_runs",
    "propose_edges",
]
