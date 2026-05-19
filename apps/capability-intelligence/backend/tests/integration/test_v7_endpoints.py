"""Integration tests for the v7.0 catalogue endpoints (Phase 1.3).

These endpoints surface the new collections introduced by the v7.0
extended-tab parser. Each test seeds the P1 fixture via
``catalogue_service.refresh_pillar`` so the assertions exercise the
actual workbook payload, not synthetic stubs.
"""

import pytest

from app.services import catalogue_service


@pytest.fixture
def seeded(client):
    """Refresh P1 into the per-test in-memory repo so the endpoints
    return live workbook data."""
    catalogue_service.refresh_pillar("P1", by="test")
    return client


def test_get_offerings_returns_deduped_list(seeded, auth_headers):
    r = seeded.get("/api/catalogue/offerings", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) > 0
    # Dedup across pillars: each offering_id appears once.
    ids = [row["offering_id"] for row in rows]
    assert len(ids) == len(set(ids))


def test_get_data_products(seeded, auth_headers):
    r = seeded.get("/api/catalogue/data-products", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) > 0
    assert all(row.get("module_id") for row in rows)


def test_get_agentforce_agents(seeded, auth_headers):
    r = seeded.get("/api/catalogue/agentforce-agents", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) > 0
    assert all(row.get("agent_id") for row in rows)


def test_get_platform_constructs(seeded, auth_headers):
    r = seeded.get("/api/catalogue/platform-constructs", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) > 0
    assert all(row.get("construct_name") for row in rows)


def test_cross_pillar_stories_filtering(seeded, auth_headers):
    r = seeded.get(
        "/api/catalogue/cross-pillar-stories?pillar_id=P1&limit=10",
        headers=auth_headers,
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) <= 10
    for row in rows:
        assert row.get("destination_pillar_id") == "P1"


def test_cross_pillar_stories_subcap_filter(seeded, auth_headers):
    # Get one subcap that has at least one cross-pillar story.
    all_rows = seeded.get(
        "/api/catalogue/cross-pillar-stories?pillar_id=P1&limit=50",
        headers=auth_headers,
    ).json()
    target = None
    for r in all_rows:
        if r.get("linked_sub_caps"):
            target = r["linked_sub_caps"][0]
            break
    if not target:
        pytest.skip("no subcap with linked_sub_caps in fixture")
    filtered = seeded.get(
        f"/api/catalogue/cross-pillar-stories?pillar_id=P1&sub_cap_id={target}",
        headers=auth_headers,
    ).json()
    assert len(filtered) >= 1
    for r in filtered:
        assert target in (r.get("linked_sub_caps") or [])


def test_completeness_endpoint(seeded, auth_headers):
    r = seeded.get(
        "/api/catalogue/completeness/P1C1.1.1",
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sub_cap_id"] == "P1C1.1.1"
    assert body.get("total_score") is not None
    assert 0 <= body["total_score"] <= 8


def test_completeness_404_for_unknown(seeded, auth_headers):
    r = seeded.get(
        "/api/catalogue/completeness/DOES.NOT.EXIST",
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_subcap_detail_includes_v7_sections(seeded, auth_headers):
    r = seeded.get("/api/catalogue/subcaps/P1C1.1.1", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    # v7.0 extensions surface alongside the existing payload
    assert "offerings" in body
    assert "data_products" in body
    assert "completeness" in body
    assert "cross_pillar_coverage" in body
    assert "cascade_simulation" in body


def test_subcap_detail_completeness_populated(seeded, auth_headers):
    """Pick a subcap that we know has a completeness row in the
    workbook (P1C1.1.1) and verify the join works at the API edge."""
    r = seeded.get("/api/catalogue/subcaps/P1C1.1.1", headers=auth_headers)
    body = r.json()
    comp = body.get("completeness")
    assert comp is not None
    assert comp["sub_cap_id"] == "P1C1.1.1"
    assert comp.get("total_score") is not None
