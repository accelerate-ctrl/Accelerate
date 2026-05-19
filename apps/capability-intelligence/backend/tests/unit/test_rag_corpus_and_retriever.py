"""Tests for the catalogue-grounded RAG corpus builder + hybrid retriever
(PRD FR-16, TRD §11).

The 6 PRD FR-16 acceptance queries are exercised at the bottom of this
module via :func:`test_fr16_acceptance_queries`. These are the queries
that must succeed before Phase 2 can be marked done per Implementation
Steps §5.
"""

import pytest

from app.services.catalogue_service import COLLECTIONS
from app.services.rag.catalogue_corpus_builder import (
    INDEX_NAME,
    rebuild_corpus,
)
from app.services.rag.hybrid_retriever import retrieve
from app.services.repository import get_repository

# ─── Builder fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def seeded_catalogue(settings_for_tests):
    """Seed a minimal cross-pillar catalogue slice that exercises every
    chunk kind the corpus builder emits."""
    repo = get_repository()
    repo.upsert(COLLECTIONS["subcaps"], "P1C1.1.1", {
        "sub_cap_id": "P1C1.1.1",
        "sub_cap_name": "Digital Strategy Document",
        "pillar_id": "P1",
        "category_id": "C1",
        "l1_capability": "Strategy Foundation",
        "description": "Define the institution's digital strategy.",
        "tier": "T1",
        "personas": ["CDO", "CIO"],
        "persona_refs": [
            {"canonical_name": "CDO", "family": "c_suite", "role_description": "Chief Data Officer"},
            {"canonical_name": "CIO", "family": "c_suite", "role_description": "Chief Info Officer"},
        ],
    })
    repo.upsert(COLLECTIONS["subcaps"], "P1C3.5.2", {
        "sub_cap_id": "P1C3.5.2",
        "sub_cap_name": "Open Banking API",
        "pillar_id": "P1",
        "category_id": "C3",
        "l1_capability": "Open Banking",
        "description": "Expose account aggregation APIs to authorised TPPs.",
        "tier": "T1",
        "personas": ["CTO"],
    })
    repo.upsert(COLLECTIONS["maturity"], "P1C1.1.1", {
        "sub_cap_id": "P1C1.1.1",
        "pillar_id": "P1",
        "m1": "Foundational — Word doc with strategy bullets.",
        "m1_features": "doc, bullets",
        "m3": "Established — quarterly OKR refresh + steering committee.",
        "m5": "Transformational — board-level AI ethics charter + KPIs.",
    })
    repo.upsert(COLLECTIONS["stories"], "P1C1.1.1.S1", {
        "story_key": "P1C1.1.1.S1",
        "pillar_id": "P1",
        "sub_cap_id": "P1C1.1.1",
        "summary": "As a CDO I want a documented strategy refresh cadence.",
    })
    repo.upsert(COLLECTIONS["l4"], "P1C1.1.1__L3-SF-FSC__strategy_authoring", {
        "sub_cap_id": "P1C1.1.1",
        "source_pillar_id": "P1",
        "l3_platform_id": "L3-SF-FSC",
        "feature_name": "Strategy authoring workspace",
        "vendor": "Salesforce",
        "detailed_description": "Strategy document authoring in Quip + Slack canvas.",
    })
    repo.upsert(COLLECTIONS["themes"], "AI::P1C1.1.1", {
        "theme": "AI",
        "sub_cap_id": "P1C1.1.1",
        "pillar_id": "P1",
        "mapping_rationale": "Strategy doc names AI initiatives.",
    })
    # An L3 platform row for structured-filter testing.
    repo.upsert(COLLECTIONS["l3"], "L3-SF-FSC", {
        "l3_id": "L3-SF-FSC",
        "name": "Salesforce Financial Services Cloud",
        "vendor": "Salesforce",
        "description": "FSC unified relationship platform.",
    })
    return repo


@pytest.fixture
def built_corpus(seeded_catalogue):
    return rebuild_corpus()


# ─── Corpus builder behaviour ──────────────────────────────────────────────


def test_rebuild_emits_chunks_for_every_kind(built_corpus):
    summary = built_corpus
    # 2 subcaps × 1 chunk + 3 M-levels on one subcap + 1 story +
    # 1 L4 feature + 1 theme mapping + 2 personas.
    assert summary.counts_by_kind["subcap"] == 2
    assert summary.counts_by_kind["maturity"] == 3  # m1, m3, m5
    assert summary.counts_by_kind["story"] == 1
    assert summary.counts_by_kind["l4_feature"] == 1
    assert summary.counts_by_kind["theme_mapping"] == 1
    assert summary.counts_by_kind["persona"] >= 2
    assert summary.total_chunks >= 9


def test_chunk_metadata_is_indexable(built_corpus, seeded_catalogue):
    """Every emitted chunk carries the metadata required by the
    retriever (kind, sub_cap_id where applicable, catalogue_version).
    """
    repo = get_repository()
    chunks = [
        r for r in repo.list("vector_index")
        if (r.get("metadata") or {}).get("catalogue_version", "").startswith("corpus-")
    ]
    assert chunks
    for c in chunks:
        meta = c["metadata"]
        assert meta["catalogue_version"].startswith("corpus-")
        assert meta.get("kind")
        if meta["kind"] in ("subcap", "maturity", "l4_feature", "theme_mapping"):
            assert meta.get("sub_cap_id")


def test_rebuild_is_idempotent(seeded_catalogue):
    """Re-running the builder must not duplicate chunks."""
    rebuild_corpus()
    first = len([
        r for r in get_repository().list("vector_index")
        if (r.get("metadata") or {}).get("catalogue_version", "").startswith("corpus-")
    ])
    rebuild_corpus()
    second = len([
        r for r in get_repository().list("vector_index")
        if (r.get("metadata") or {}).get("catalogue_version", "").startswith("corpus-")
    ])
    assert first == second


def test_pillar_scoped_rebuild_only_touches_target(seeded_catalogue):
    """A pillar-scoped rebuild must drop only that pillar's chunks."""
    repo = get_repository()
    rebuild_corpus()
    repo.upsert(COLLECTIONS["subcaps"], "P2C1.1.1", {
        "sub_cap_id": "P2C1.1.1",
        "sub_cap_name": "P2 test",
        "pillar_id": "P2",
        "category_id": "C1",
        "l1_capability": "test",
        "description": "x",
    })
    rebuild_corpus(pillar_id="P2")
    chunks = [
        r for r in repo.list("vector_index")
        if (r.get("metadata") or {}).get("catalogue_version", "").startswith("corpus-")
    ]
    pillars = {(c["metadata"] or {}).get("pillar_id") for c in chunks}
    assert "P1" in pillars
    assert "P2" in pillars


# ─── Hybrid retriever ──────────────────────────────────────────────────────


def test_structured_filter_resolves_exact_subcap_id(built_corpus):
    """A query containing a precise sub_cap_id should return that
    subcap as the #1 hit via the structured filter signal.
    """
    hits = retrieve("Tell me about P1C3.5.2 and how to extend it.", top_k=5)
    assert hits
    assert hits[0].metadata.get("sub_cap_id") == "P1C3.5.2"
    assert "structured" in hits[0].signals


def test_dense_signal_matches_semantic_paraphrase(built_corpus):
    """Even without exact term matches, the dense signal must surface
    the open-banking subcap for a paraphrased query.
    """
    hits = retrieve("How do banks expose account data to fintech partners?", top_k=10)
    target = next((h for h in hits if h.metadata.get("sub_cap_id") == "P1C3.5.2"), None)
    assert target is not None
    assert "dense" in target.signals


def test_bm25_signal_matches_keyword_overlap(built_corpus):
    """BM25 surfaces hits whose chunk text shares query keywords
    even when dense embedding similarity is lower."""
    hits = retrieve("strategy refresh cadence steering committee", top_k=10)
    assert any("bm25" in h.signals for h in hits)


def test_l3_platform_resolved_via_structured_filter(built_corpus):
    hits = retrieve("compare nCino vs L3-SF-FSC for advisor workflow", top_k=10)
    target = next((h for h in hits if h.metadata.get("source_id") == "L3-SF-FSC"), None)
    assert target is not None
    assert "structured" in target.signals


def test_rrf_fuses_multi_signal_hits_to_higher_rank(built_corpus):
    """When the same doc is returned by multiple signals it should
    score higher than docs returned by only one."""
    hits = retrieve("Open Banking API P1C3.5.2", top_k=10)
    top = hits[0]
    assert top.metadata.get("sub_cap_id") == "P1C3.5.2"
    assert len(top.signals) >= 2


def test_returns_empty_on_unrelated_query(built_corpus):
    """Garbage query that matches nothing should return empty (or near-
    empty) results, not raise."""
    hits = retrieve("xyzzy frobnicate qux", top_k=10)
    assert isinstance(hits, list)


# ─── FR-16 acceptance queries ──────────────────────────────────────────────
#
# Per PRD §9 and Implementation Steps §5, these six queries gate Phase 2.
# Each must return a hit whose ``sub_cap_id`` matches the expected
# target. The queries are intentionally varied in shape (exact id,
# vendor name, persona phrasing, capability keyword) to exercise all
# three retrieval signals.


@pytest.mark.parametrize("query,expected_sub_cap_id", [
    ("Tell me about P1C1.1.1", "P1C1.1.1"),
    ("strategy refresh cadence", "P1C1.1.1"),
    ("CDO mandate for institutional strategy", "P1C1.1.1"),
    ("open banking account aggregation", "P1C3.5.2"),
    ("L3-SF-FSC strategy authoring workspace", "P1C1.1.1"),
    ("How does P1C1.1.1 connect to AI initiatives?", "P1C1.1.1"),
])
def test_fr16_acceptance_queries(built_corpus, query, expected_sub_cap_id):
    hits = retrieve(query, top_k=10)
    assert hits, f"query produced no hits: {query!r}"
    matched = [h for h in hits if h.metadata.get("sub_cap_id") == expected_sub_cap_id]
    assert matched, (
        f"query {query!r} did not return expected sub_cap_id {expected_sub_cap_id}; "
        f"got top: {[h.metadata.get('sub_cap_id') for h in hits[:5]]}"
    )


def test_index_name_constant_exported():
    assert INDEX_NAME == "catalogue_ontology"
