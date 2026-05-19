"""Catalogue corpus builder for RAG retrieval (PRD FR-16).

Walks the per-pillar collections produced by ``catalogue_service`` and
``sheets_parser`` (Phase 1.3) and emits one chunk per entity into a
single ``catalogue_ontology`` vector-store index. Triggered after every
catalogue refresh so the corpus is always in sync with the workbook.

Chunk shapes (one per entity kind):

- **subcap**         : identity + description + L1 + personas
- **maturity**       : one chunk per M-level (M1..M5) with its descriptor
                        text + feature list
- **story**          : story summary + sub_cap_id
- **l4_feature**     : feature title + sub_cap_id + l3_platform_id
- **theme_mapping**  : theme name + sub_cap_id + rationale (when present)
- **persona**        : canonical persona name + role description

Each chunk carries:

- ``kind``           — one of the seven entity kinds
- ``sub_cap_id``     — when applicable (drives the structured filter)
- ``pillar_id``      — coarse pillar bucket for diversity-aware re-rank
- ``catalogue_version`` — the ingest run that produced this chunk
- ``source_id``      — the originating workbook row id

The builder always upserts under a *deterministic* doc id so re-running
the builder against the same catalogue is idempotent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from ..catalogue_service import COLLECTIONS
from ..llm.vector_store import VectorStore
from ..repository import get_repository

logger = logging.getLogger(__name__)

# Single canonical index for the entire catalogue corpus. Keeps lookup
# fast even at full v7.0 scale (~851 subcaps × ~7 kinds = ~22k chunks).
INDEX_NAME = "catalogue_ontology"


@dataclass
class BuildSummary:
    started_at: str
    completed_at: str
    counts_by_kind: dict[str, int]
    total_chunks: int


def _subcap_chunk_text(sub: dict) -> str:
    """Compact identity blurb for a subcap chunk."""
    parts = [
        f"{sub.get('sub_cap_id', '?')} — {sub.get('sub_cap_name', '?')}",
        f"Pillar {sub.get('pillar_id', '?')}, Category {sub.get('category_id', '?')}, "
        f"L1 {sub.get('l1_capability', '?')}",
    ]
    if sub.get("description"):
        parts.append(str(sub["description"]))
    if sub.get("solution_type"):
        parts.append(f"Solution type: {sub['solution_type']}")
    if sub.get("tier"):
        parts.append(f"Tier: {sub['tier']}")
    personas = sub.get("personas") or []
    if personas:
        parts.append("Personas: " + "; ".join(personas[:8]))
    return "\n".join(parts)


def _maturity_chunk_text(level: str, descriptor: str, features: str | None) -> str:
    out = [f"{level.upper()}: {descriptor}"]
    if features:
        out.append(f"Feature anchors: {features}")
    return "\n".join(out)


def _persona_canonical(repo) -> list[dict]:
    """Pull distinct persona names + roles across every subcap row."""
    seen: dict[str, dict] = {}
    for sc in repo.list(COLLECTIONS["subcaps"]):
        for ref in sc.get("persona_refs") or []:
            if not isinstance(ref, dict):
                continue
            name = (ref.get("canonical_name") or "").strip()
            if not name:
                continue
            existing = seen.get(name.lower())
            if existing is None:
                seen[name.lower()] = {
                    "canonical_name": name,
                    "family": ref.get("family"),
                    "role_description": ref.get("role_description"),
                    "subcap_count": 1,
                }
            else:
                existing["subcap_count"] += 1
    return list(seen.values())


# ─── Public API ────────────────────────────────────────────────────────────


def rebuild_corpus(*, pillar_id: str | None = None) -> BuildSummary:
    """Walk every persisted catalogue entity and re-emit chunks into the
    ``catalogue_ontology`` vector store.

    When ``pillar_id`` is given, only that pillar's slice is rebuilt
    (the existing pillar chunks are dropped first to keep the index in
    sync with a partial refresh).

    Wrapped in :meth:`Repository.defer_persist` so the ~22k chunk
    upserts at full v7.0 scale don't generate a disk flush per row —
    without this the P1 refresh + corpus rebuild ballooned the test
    suite from ~10s to >5 minutes.
    """
    started = datetime.now(timezone.utc)
    repo = get_repository()
    vs = VectorStore()
    with repo.defer_persist():
        return _rebuild_corpus_inner(
            started=started, repo=repo, vs=vs, pillar_id=pillar_id,
        )


def _rebuild_corpus_inner(
    *, started, repo, vs, pillar_id: str | None,
) -> BuildSummary:
    counts: dict[str, int] = {
        "subcap": 0,
        "maturity": 0,
        "story": 0,
        "l4_feature": 0,
        "theme_mapping": 0,
        "persona": 0,
    }
    catalogue_version = f"corpus-{int(started.timestamp())}"

    # Drop the previous slice. The InMemoryRepository indexes by doc_id
    # so iterating + deleting is O(N); good enough for ~22k chunks.
    _drop_prior_chunks(vs, pillar_id=pillar_id)

    # ── Subcaps ──
    for sub in repo.list(COLLECTIONS["subcaps"]):
        if pillar_id and sub.get("pillar_id") != pillar_id:
            continue
        sid = sub.get("sub_cap_id")
        if not sid:
            continue
        vs.upsert(
            f"subcap::{sid}",
            _subcap_chunk_text(sub),
            metadata={
                "kind": "subcap",
                "sub_cap_id": sid,
                "pillar_id": sub.get("pillar_id"),
                "title": sub.get("sub_cap_name") or sid,
                "catalogue_version": catalogue_version,
                "source_id": sid,
            },
        )
        counts["subcap"] += 1

    # ── Maturity descriptors (5 per subcap) ──
    for m in repo.list(COLLECTIONS["maturity"]):
        if pillar_id and m.get("pillar_id") != pillar_id:
            continue
        sid = m.get("sub_cap_id")
        if not sid:
            continue
        for level in ("m1", "m2", "m3", "m4", "m5"):
            descriptor = m.get(level)
            if not descriptor:
                continue
            features = m.get(f"{level}_features")
            vs.upsert(
                f"maturity::{sid}::{level}",
                _maturity_chunk_text(level, str(descriptor), features),
                metadata={
                    "kind": "maturity",
                    "sub_cap_id": sid,
                    "pillar_id": m.get("pillar_id"),
                    "title": f"{sid} {level.upper()} descriptor",
                    "level": level.upper(),
                    "catalogue_version": catalogue_version,
                    "source_id": sid,
                },
            )
            counts["maturity"] += 1

    # ── Stories ──
    for s in repo.list(COLLECTIONS["stories"]):
        if pillar_id and s.get("pillar_id") != pillar_id:
            continue
        key = s.get("story_key")
        summary = s.get("summary") or s.get("story_title") or ""
        if not key or not summary:
            continue
        sid = s.get("sub_cap_id")
        vs.upsert(
            f"story::{key}",
            f"{key}: {summary}",
            metadata={
                "kind": "story",
                "sub_cap_id": sid,
                "pillar_id": s.get("pillar_id"),
                "title": key,
                "catalogue_version": catalogue_version,
                "source_id": key,
            },
        )
        counts["story"] += 1

    # ── L4 features ──
    for f in repo.list(COLLECTIONS["l4"]):
        if pillar_id and f.get("source_pillar_id") != pillar_id:
            continue
        sid = f.get("sub_cap_id")
        feat = f.get("feature_name")
        if not sid or not feat:
            continue
        body_parts = [feat]
        if f.get("detailed_description"):
            body_parts.append(str(f["detailed_description"]))
        if f.get("vendor"):
            body_parts.append(f"Vendor: {f['vendor']}")
        if f.get("l3_platform_id"):
            body_parts.append(f"L3: {f['l3_platform_id']}")
        doc_id = f"l4::{sid}::{f.get('l3_platform_id') or '-'}::{feat[:40]}"
        vs.upsert(
            doc_id,
            "\n".join(body_parts),
            metadata={
                "kind": "l4_feature",
                "sub_cap_id": sid,
                "pillar_id": f.get("source_pillar_id"),
                "title": feat,
                "catalogue_version": catalogue_version,
                "source_id": doc_id,
            },
        )
        counts["l4_feature"] += 1

    # ── Theme mappings ──
    for t in repo.list(COLLECTIONS["themes"]):
        if pillar_id and t.get("pillar_id") != pillar_id:
            continue
        theme = t.get("theme") or t.get("theme_name")
        sid = t.get("sub_cap_id")
        if not theme or not sid:
            continue
        rationale = t.get("mapping_rationale") or t.get("rationale") or ""
        body = f"{theme} → {sid}"
        if rationale:
            body += f": {rationale}"
        vs.upsert(
            f"theme::{theme}::{sid}",
            body,
            metadata={
                "kind": "theme_mapping",
                "sub_cap_id": sid,
                "pillar_id": t.get("pillar_id"),
                "title": f"{theme} on {sid}",
                "catalogue_version": catalogue_version,
                "source_id": f"{theme}::{sid}",
            },
        )
        counts["theme_mapping"] += 1

    # ── Personas (deduped across pillars) ──
    if not pillar_id:
        for p in _persona_canonical(repo):
            name = p["canonical_name"]
            body = f"Persona: {name}"
            if p.get("role_description"):
                body += f" — {p['role_description']}"
            if p.get("family"):
                body += f"\nFamily: {p['family']}"
            if p.get("subcap_count"):
                body += f"\nReferenced by {p['subcap_count']} subcap(s)"
            vs.upsert(
                f"persona::{name.lower().replace(' ', '_')}",
                body,
                metadata={
                    "kind": "persona",
                    "title": name,
                    "family": p.get("family"),
                    "catalogue_version": catalogue_version,
                    "source_id": name,
                },
            )
            counts["persona"] += 1

    completed = datetime.now(timezone.utc)
    total = sum(counts.values())
    logger.info(
        "catalogue corpus rebuilt: %d chunks across %d kinds in %.1fs",
        total, sum(1 for v in counts.values() if v > 0),
        (completed - started).total_seconds(),
    )
    return BuildSummary(
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        counts_by_kind=counts,
        total_chunks=total,
    )


def _drop_prior_chunks(vs: VectorStore, *, pillar_id: str | None) -> None:
    """Remove existing catalogue_ontology chunks before rebuild.

    Without this, a partial pillar refresh would leave stale chunks
    from prior runs in the index, polluting retrieval results.
    """
    repo = get_repository()
    target = "vector_index"  # the InMemory store's collection name
    rows = repo.list(target)
    for r in rows:
        meta = r.get("metadata") or {}
        if pillar_id and meta.get("pillar_id") != pillar_id:
            continue
        if meta.get("catalogue_version", "").startswith("corpus-"):
            repo.delete(target, r["doc_id"])


__all__ = ["BuildSummary", "INDEX_NAME", "rebuild_corpus"]
