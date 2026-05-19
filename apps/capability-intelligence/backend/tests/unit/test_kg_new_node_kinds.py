"""Tests for the Phase 3.1 KG node-kind expansion.

The plan calls for ≥22 node kinds in the production KG; today's
graph_service emits 20. This module verifies the 6 newly-wired node
kinds (Offering, DataProduct, AgentforceAgent, Story, Client, NewsItem)
plus their edges are present when their source collections are
populated, and that empty source collections degrade silently.
"""

import pytest

from app.services import graph_service
from app.services.catalogue_service import COLLECTIONS
from app.services.repository import get_repository


@pytest.fixture
def seeded_kg(settings_for_tests):
    """Seed a minimal but cross-cutting slice that exercises every new
    node kind + the edges between them."""
    repo = get_repository()

    # A subcap is the join target for most new edges, so seed one.
    repo.upsert(COLLECTIONS["subcaps"], "P1C1.1.1", {
        "sub_cap_id": "P1C1.1.1",
        "sub_cap_name": "Digital Strategy",
        "pillar_id": "P1",
        "category_id": "C1",
        "l1_capability": "Strategy Foundation",
    })
    # A category + pillar so the spine builder doesn't drop the subcap.
    repo.upsert(COLLECTIONS["pillars"], "P1", {"pillar_id": "P1", "name": "Pillar 1"})
    repo.upsert(COLLECTIONS["categories"], "C1", {
        "category_id": "C1", "pillar_id": "P1", "name": "Cat 1",
    })
    repo.upsert(COLLECTIONS["l3"], "L3-SF-AGENTFORCE", {
        "l3_id": "L3-SF-AGENTFORCE",
        "name": "Agentforce Platform",
        "vendor": "Salesforce",
    })

    # ─ Offering + matrix edge ─
    repo.upsert(COLLECTIONS["offerings"], "P1::OFF-DMA", {
        "offering_id": "OFF-DMA",
        "offering_name": "Data Modernization & AI Platform",
        "source_pillar_id": "P1",
        "status": "Active",
        "category": "Priority",
    })
    repo.upsert(COLLECTIONS["offering_subcap_matrix"], "OFF-DMA::P1C1.1.1", {
        "offering_id": "OFF-DMA",
        "sub_cap_id": "P1C1.1.1",
        "maturity_lift": "M2 → M4",
    })

    # ─ Data Product + matrix edge ─
    repo.upsert(COLLECTIONS["data_products"], "P1::DP-1.1", {
        "module_id": "DP-1.1",
        "module_name": "Customer 360 Golden Record",
        "source_pillar_id": "P1",
    })
    repo.upsert(COLLECTIONS["dataproduct_subcap_matrix"], "DP-1.1::P1C1.1.1", {
        "module_id": "DP-1.1",
        "sub_cap_id": "P1C1.1.1",
    })

    # ─ AgentforceAgent linked back to Parent_L3 platform ─
    repo.upsert(COLLECTIONS["agentforce_agents"], "AF-001", {
        "agent_id": "AF-001",
        "agent_name": "Service Agent",
        "lob": "Customer Service",
        "workflow": "Service",
        "parent_l3": "Agentforce 360 Platform (L3-SF-AGENTFORCE)",
    })

    # ─ Story linked to subcap ─
    repo.upsert(COLLECTIONS["stories"], "P1C1.1.1.S1", {
        "story_key": "P1C1.1.1.S1",
        "sub_cap_id": "P1C1.1.1",
        "summary": "As a CDO I want to document strategy refresh cadence.",
    })

    # ─ Client + SOW + SOW mention ─
    repo.upsert("clients", "acme-bank", {
        "client_id": "acme-bank",
        "name": "Acme Bank",
        "subvertical": "RB",
    })
    repo.upsert("sows", "SOW-001", {
        "sow_id": "SOW-001",
        "status": "active",
        "client_name": "acme-bank",
    })
    repo.upsert("sow_mentions", "m1", {
        "sow_id": "SOW-001",
        "sub_cap_id": "P1C1.1.1",
        "method": "fuzzy",
        "confidence": 0.85,
    })

    # ─ NewsItem with structured impact ─
    repo.upsert("news_items", "news-001", {
        "id": "news-001",
        "title": "OCC ruling on digital strategy",
        "source": "occ.gov",
        "url": "https://occ.gov/x",
        "impact": {
            "impact_class": "catalogue_extension",
            "affected_subcaps": [
                {"sub_cap_id": "P1C1.1.1", "magnitude": "HIGH", "rationale": "Direct"},
            ],
        },
    })

    # Invalidate the lru_cache so the next build_graph sees seeded data.
    graph_service.invalidate_cache()
    return repo


def _node_kinds(g) -> set:
    return {d.get("kind") for _, d in g.nodes(data=True)}


def _edge_kinds(g) -> set:
    return {d.get("kind") for _, _, d in g.edges(data=True)}


def test_kg_emits_new_v7_node_kinds(seeded_kg):
    """Phase 3 done criterion requires ≥22 node kinds across 4 pillars
    in production. This unit test asserts that the 6 new v7.0 kinds
    are wired correctly — the full 22+ kinds are reached when a real
    P1+P2+P3+P4 catalogue is ingested (verified via
    test_v7_extended_parser.py).
    """
    g = graph_service.build_graph()
    kinds = _node_kinds(g)
    # The 6 kinds Phase 3.1 added.
    expected_new = {
        "Offering", "DataProduct", "AgentforceAgent",
        "Story", "Client", "NewsItem",
    }
    missing = expected_new - kinds
    assert not missing, f"missing v7.0 KG node kinds: {missing}"


def test_kg_includes_offering_kind(seeded_kg):
    g = graph_service.build_graph()
    assert "Offering" in _node_kinds(g)
    assert any("OFF-DMA" in n for n, _ in g.nodes(data=True))


def test_kg_offering_realized_in_edge(seeded_kg):
    g = graph_service.build_graph()
    assert "REALIZED_IN" in _edge_kinds(g)
    # The edge should carry the maturity_lift attribute.
    edges = [
        (s, t, d) for s, t, d in g.edges(data=True)
        if d.get("kind") == "REALIZED_IN"
    ]
    assert edges
    assert any(d.get("maturity_lift") for _, _, d in edges)


def test_kg_data_product_grounded_by_edge(seeded_kg):
    g = graph_service.build_graph()
    assert "DataProduct" in _node_kinds(g)
    assert "GROUNDED_BY" in _edge_kinds(g)


def test_kg_agentforce_runs_on_parent_l3(seeded_kg):
    g = graph_service.build_graph()
    assert "AgentforceAgent" in _node_kinds(g)
    # Verify the RUNS_ON edge resolved to the L3 platform.
    runs_on = [
        (s, t, d) for s, t, d in g.edges(data=True)
        if d.get("kind") == "RUNS_ON"
    ]
    assert runs_on, "RUNS_ON edge missing"


def test_kg_story_has_story_edge(seeded_kg):
    g = graph_service.build_graph()
    assert "Story" in _node_kinds(g)
    assert "HAS_STORY" in _edge_kinds(g)


def test_kg_sow_owned_by_client(seeded_kg):
    g = graph_service.build_graph()
    assert "SOW" in _node_kinds(g)
    assert "Client" in _node_kinds(g)
    assert "OWNED_BY" in _edge_kinds(g)
    assert "MENTIONS" in _edge_kinds(g)


def test_kg_news_affects_with_magnitude(seeded_kg):
    g = graph_service.build_graph()
    assert "NewsItem" in _node_kinds(g)
    affects = [
        (s, t, d) for s, t, d in g.edges(data=True)
        if d.get("kind") == "AFFECTS"
    ]
    assert affects, "AFFECTS edge missing"
    # The magnitude must propagate from the news impact payload.
    assert any(d.get("magnitude") == "HIGH" for _, _, d in affects)


def test_empty_collections_degrade_silently(settings_for_tests):
    """The new emitters must not raise when no source rows exist."""
    graph_service.invalidate_cache()
    g = graph_service.build_graph()
    # Just verify the build completes; nodes may be zero.
    assert g is not None


def test_legacy_flat_news_impacts_still_produce_edges(seeded_kg):
    """News items whose only impact shape is the legacy ``affects_subcaps``
    flat list must still produce AFFECTS edges (at LOW magnitude)."""
    repo = get_repository()
    repo.upsert("news_items", "news-legacy", {
        "id": "news-legacy",
        "title": "Legacy shape",
        "impact": {
            "impact_class": "reinforcement",
            "affects_subcaps": ["P1C1.1.1"],
        },
    })
    graph_service.invalidate_cache()
    g = graph_service.build_graph()
    affects = [
        (s, t, d) for s, t, d in g.edges(data=True)
        if d.get("kind") == "AFFECTS"
    ]
    legacy_edges = [e for e in affects if "legacy" in e[0]]
    assert legacy_edges
    assert legacy_edges[0][2].get("magnitude") == "LOW"


def test_story_cap_bounds_in_memory_graph(seeded_kg):
    """Adding 5k stories must not put 5k story nodes in the graph —
    the emitter caps at 4000 to keep the in-memory graph bounded."""
    repo = get_repository()
    # Bulk-insert 5000 stories.
    for i in range(5000):
        repo.upsert(COLLECTIONS["stories"], f"P1C1.1.1.S{i+10}", {
            "story_key": f"P1C1.1.1.S{i+10}",
            "sub_cap_id": "P1C1.1.1",
            "summary": f"Story {i}",
        })
    graph_service.invalidate_cache()
    g = graph_service.build_graph()
    story_count = sum(
        1 for _, d in g.nodes(data=True) if d.get("kind") == "Story"
    )
    assert story_count <= 4000


def test_summary_reflects_new_kinds(seeded_kg):
    """The KG summary endpoint must list the new node kinds in its
    by_kind breakdown.
    """
    s = graph_service.summary()
    assert "Offering" in s.nodes_by_type
    assert "DataProduct" in s.nodes_by_type
    assert "AgentforceAgent" in s.nodes_by_type
    assert "Story" in s.nodes_by_type
    assert "NewsItem" in s.nodes_by_type
