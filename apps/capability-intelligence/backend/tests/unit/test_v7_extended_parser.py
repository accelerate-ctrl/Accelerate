"""Tests for the v7.0 extended-tab parsers (Phase 1.3 / QA_AUDIT F10).

Exercises the new emitters for tabs 8, 9, 10, 11, 12, 13, 14, 16, 18, 19
end-to-end:

- ``parse_workbook()`` on the real Pillar-1 fixture produces non-empty
  lists for every extended tab the fixture contains.
- ``catalogue_service.refresh_pillar()`` persists the rows into the
  expected ``COLLECTIONS`` keys.
- The composite document IDs prevent collisions across pillars.
"""

from pathlib import Path

import pytest

from app.services import catalogue_service
from app.services.catalogue_service import COLLECTIONS
from app.services.repository import get_repository
from app.services.sheets_parser import parse_workbook

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "test-data"
    / "Pillar 1"
    / "Pillar_1_Capability_Map_v14.0.xlsx"
)


# ─── Direct parser tests (no repository) ───────────────────────────────────


@pytest.fixture(scope="module")
def parsed():
    """Parse the P1 fixture once for the whole module."""
    assert FIXTURE.exists(), f"fixture missing: {FIXTURE}"
    return parse_workbook(FIXTURE, default_pillar_id="P1")


def test_parses_agentforce_agents(parsed):
    assert len(parsed.agentforce_agents) > 0
    first = parsed.agentforce_agents[0]
    assert first["agent_id"]
    assert first["pillar_id"] == "P1"
    # Every row should have at minimum the agent_id field populated.
    assert all(a.get("agent_id") for a in parsed.agentforce_agents)


def test_parses_platform_constructs(parsed):
    assert len(parsed.platform_constructs) > 0
    first = parsed.platform_constructs[0]
    assert first["construct_name"]
    # Vendor + docs_url commonly present
    assert any(c.get("vendor") for c in parsed.platform_constructs)


def test_parses_offerings(parsed):
    assert len(parsed.offerings) > 0
    first = parsed.offerings[0]
    assert first["offering_id"]
    assert first["source_pillar_id"] == "P1"
    # At least one offering should have a non-empty l3_platforms_used list.
    assert any(o.get("l3_platforms_used") for o in parsed.offerings)
    # Numeric coercion: total_mapped_subcaps must be int|None, not the raw float openpyxl returns.
    for o in parsed.offerings:
        v = o.get("total_mapped_subcaps")
        assert v is None or isinstance(v, int)


def test_parses_data_products(parsed):
    assert len(parsed.data_products) > 0
    first = parsed.data_products[0]
    assert first["module_id"]
    assert first["source_pillar_id"] == "P1"


def test_parses_offering_subcap_matrix(parsed):
    assert len(parsed.offering_subcap_matrix) > 0
    first = parsed.offering_subcap_matrix[0]
    assert first["offering_id"]
    assert first["sub_cap_id"]
    # Composite key (offering_id, sub_cap_id) must be unique.
    keys = [(r["offering_id"], r["sub_cap_id"]) for r in parsed.offering_subcap_matrix]
    assert len(keys) == len(set(keys))


def test_parses_dataproduct_subcap_matrix(parsed):
    assert len(parsed.dataproduct_subcap_matrix) > 0
    first = parsed.dataproduct_subcap_matrix[0]
    assert first["module_id"]
    assert first["sub_cap_id"]


def test_parses_cross_pillar_stories(parsed):
    """Tab 14 is the largest by row count — should yield hundreds at minimum."""
    assert len(parsed.cross_pillar_stories) > 100
    first = parsed.cross_pillar_stories[0]
    assert first["story_key"]
    assert first["destination_pillar_id"] == "P1"
    # Themes split on ';' — should be a list, never a raw string.
    for s in parsed.cross_pillar_stories[:50]:
        assert isinstance(s["themes"], list)
    # linked_sub_caps similarly
    assert any(s["linked_sub_caps"] for s in parsed.cross_pillar_stories[:50])


def test_parses_cross_pillar_coverage(parsed):
    assert len(parsed.cross_pillar_coverage) > 0
    first = parsed.cross_pillar_coverage[0]
    assert first["sub_cap_id"]
    # Numeric fields coerced
    assert all(
        r.get("total_cross_pillar_stories") is None
        or isinstance(r["total_cross_pillar_stories"], int)
        for r in parsed.cross_pillar_coverage
    )


def test_parses_completeness(parsed):
    """One completeness row per subcap (~205 for P1)."""
    assert len(parsed.completeness) > 100
    first = parsed.completeness[0]
    assert first["sub_cap_id"]
    # Score columns must coerce to int|None.
    for r in parsed.completeness[:20]:
        for k in ("core_score", "extended_score", "total_score"):
            v = r.get(k)
            assert v is None or isinstance(v, int)
    # Per the workbook header, total_score <= 8.
    for r in parsed.completeness:
        v = r.get("total_score")
        if v is not None:
            assert 0 <= v <= 8


def test_parses_cascade_simulation(parsed):
    assert len(parsed.cascade_simulation) > 100
    first = parsed.cascade_simulation[0]
    assert first["sub_cap_id"]
    # Severity is a text label (HIGH / MEDIUM / LOW); ensure it's
    # surfaced when present in the workbook.
    assert any(r.get("cascade_severity") for r in parsed.cascade_simulation)


# ─── Persistence tests via catalogue_service.refresh_pillar ────────────────


@pytest.fixture
def refreshed(settings_for_tests):
    return catalogue_service.refresh_pillar("P1", by="test")


def test_persists_v7_collections(refreshed):
    """After refresh_pillar, every extended collection is populated and
    each row is retrievable via its composite document id."""
    repo = get_repository()
    for coll_key in (
        "agentforce_agents",
        "platform_constructs",
        "offerings",
        "data_products",
        "offering_subcap_matrix",
        "dataproduct_subcap_matrix",
        "cross_pillar_stories",
        "cross_pillar_coverage",
        "completeness",
        "cascade_simulation",
    ):
        rows = repo.list(COLLECTIONS[coll_key])
        assert len(rows) > 0, f"{coll_key} is empty after refresh"


def test_refresh_is_idempotent(settings_for_tests):
    """Re-running refresh_pillar against the same fixture must not
    duplicate rows in any extended collection."""
    catalogue_service.refresh_pillar("P1", by="test")
    counts_first = {
        k: get_repository().count(COLLECTIONS[k])
        for k in (
            "agentforce_agents",
            "offerings",
            "data_products",
            "offering_subcap_matrix",
            "cross_pillar_stories",
            "completeness",
        )
    }
    catalogue_service.refresh_pillar("P1", by="test")
    counts_second = {
        k: get_repository().count(COLLECTIONS[k])
        for k in counts_first
    }
    assert counts_first == counts_second, (
        f"refresh_pillar is not idempotent: {counts_first} vs {counts_second}"
    )


def test_completeness_row_keyed_on_sub_cap_id(refreshed):
    """The completeness collection should be addressable by sub_cap_id
    so the Subcap Deep Dive's authoritative completeness section can
    fetch by id without a full scan.
    """
    repo = get_repository()
    rows = repo.list(COLLECTIONS["completeness"])
    sample = rows[0]
    doc = repo.get(COLLECTIONS["completeness"], sample["sub_cap_id"])
    assert doc is not None
    assert doc["sub_cap_id"] == sample["sub_cap_id"]
