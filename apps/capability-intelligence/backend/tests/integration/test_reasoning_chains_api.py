"""Reasoning Chains API — exercises both consultant_loop and ChainEmitter rows.

After Phase 2.4 the chain collection is populated by multiple emitters:
- consultant_loop (full 7-step chains)
- reasoning_chain_emitter (lightweight chains from news, partner intel, etc.)

These tests verify the API surfaces both shapes and supports the new
operation filter + operations summary endpoint.
"""

import pytest

from app.services.reasoning_chain_emitter import emit_chain
from app.services.repository import get_repository


@pytest.fixture
def seeded_chains(client):
    """Stage chains from multiple operations to exercise filtering."""
    with emit_chain(operation="news_impact", sub_cap_id="P1C1.1.1") as c:
        c.step("retrieve")
        c.step("llm")
        c.step("validate")
    with emit_chain(operation="news_impact", sub_cap_id="P1C2.1.1") as c:
        c.step("retrieve")
    with emit_chain(operation="partner_release_extract") as c:
        c.step("retrieve")
        c.step("llm")
    # Also stage a synthetic consultant_loop-style chain so the
    # heterogeneity is exercised.
    get_repository().upsert(
        "reasoning_chains",
        "chain-loop-fake",
        {
            "chain_id": "chain-loop-fake",
            "sub_cap_id": "P1C3.1.1",
            "started_at": "2026-05-19T08:00:00Z",
            "steps": [],
            "sources": [],
            "output": {},
            "overall": "pass",
            "total_cost_usd": 0.02,
            # No 'operation' key → simulates a legacy consultant_loop row.
        },
    )
    return client


def test_list_returns_all_chain_shapes(seeded_chains, auth_headers):
    r = seeded_chains.get("/api/reasoning-chains?limit=50", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()
    chain_ids = {row["chain_id"] for row in rows}
    # All four chains visible.
    assert "chain-loop-fake" in chain_ids
    assert any(row.get("operation") == "news_impact" for row in rows)
    assert any(row.get("operation") == "partner_release_extract" for row in rows)


def test_operation_filter_narrows_results(seeded_chains, auth_headers):
    r = seeded_chains.get(
        "/api/reasoning-chains?operation=news_impact&limit=50",
        headers=auth_headers,
    )
    rows = r.json()
    assert len(rows) >= 2
    for row in rows:
        assert row["operation"] == "news_impact"


def test_sub_cap_id_filter_works_across_shapes(seeded_chains, auth_headers):
    r = seeded_chains.get(
        "/api/reasoning-chains?sub_cap_id=P1C3.1.1",
        headers=auth_headers,
    )
    rows = r.json()
    assert any(row["chain_id"] == "chain-loop-fake" for row in rows)


def test_operations_endpoint_returns_counts(seeded_chains, auth_headers):
    r = seeded_chains.get("/api/reasoning-chains/operations", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["operations"]["news_impact"] == 2
    assert body["operations"]["partner_release_extract"] == 1
    # The legacy row without an explicit operation is bucketed as
    # consultant_loop.
    assert body["operations"]["consultant_loop"] >= 1
    assert body["total"] >= 4


def test_get_chain_by_id_works_for_emitter_chains(seeded_chains, auth_headers):
    # Grab one emitter chain's id from the list endpoint.
    rows = seeded_chains.get(
        "/api/reasoning-chains?operation=news_impact",
        headers=auth_headers,
    ).json()
    target = rows[0]["chain_id"]
    r = seeded_chains.get(f"/api/reasoning-chains/{target}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["chain_id"] == target
    assert body["operation"] == "news_impact"


def test_get_chain_404_for_unknown(seeded_chains, auth_headers):
    r = seeded_chains.get(
        "/api/reasoning-chains/chain-does-not-exist",
        headers=auth_headers,
    )
    assert r.status_code == 404
