"""Tests for the cross-pillar canonical entity service (Phase 1.4)."""

import pytest

from app.services import canonical_entity_service as svc
from app.services.catalogue_service import COLLECTIONS
from app.services.repository import get_repository


@pytest.fixture
def seeded_cross_pillar(settings_for_tests):
    """Seed the same offering / data-product / L3 platform across two
    pillars to exercise the dedup + provenance machinery."""
    repo = get_repository()

    # Offering OFF-DMA appears in P1 and P3 with different mapping counts.
    repo.upsert(COLLECTIONS["offerings"], "P1::OFF-DMA", {
        "offering_id": "OFF-DMA",
        "offering_name": "Data Modernization & AI Platform",
        "category": "Priority",
        "source_pillar_id": "P1",
        "total_mapped_subcaps": 13,
        "active_mapped_subcaps": 13,
        "linkage_health_pct": 1.0,
        "reference_url": "https://example.com/dma",
    })
    repo.upsert(COLLECTIONS["offerings"], "P3::OFF-DMA", {
        "offering_id": "OFF-DMA",
        "offering_name": "Data Modernization & AI Platform",
        "category": "Priority",
        "source_pillar_id": "P3",
        "total_mapped_subcaps": 9,
        "active_mapped_subcaps": 7,
        "linkage_health_pct": 0.77,
        "reference_url": "https://example.com/dma",
    })

    # L3 platform appears in both pillars too.
    repo.upsert(COLLECTIONS["l3"], "L3-DB-LAKEHOUSE", {
        "l3_id": "L3-DB-LAKEHOUSE",
        "name": "Databricks Lakehouse",
        "vendor": "Databricks",
        "source_pillar_id": "P1",
    })
    # A second pillar's view of the same L3 with a slightly different
    # name — triggers divergence flag.
    repo.upsert(COLLECTIONS["l3"], "L3-DB-LAKEHOUSE-P3", {
        "l3_id": "L3-DB-LAKEHOUSE",
        "name": "Databricks Lakehouse (renamed)",
        "vendor": "Databricks",
        "source_pillar_id": "P3",
    })

    # Data product only present in P1 — should still appear in canonical.
    repo.upsert(COLLECTIONS["data_products"], "P1::DP-1.1", {
        "module_id": "DP-1.1",
        "module_name": "Customer 360 Golden Record",
        "category": "Identity & Golden Record",
        "source_pillar_id": "P1",
        "total_mapped_subcaps": 1,
    })

    return svc.rebuild_canonical_entities()


def test_rebuild_returns_counts_by_kind(seeded_cross_pillar):
    summary = seeded_cross_pillar
    assert summary.counts_by_kind["Offering"] == 1
    assert summary.counts_by_kind["L3Platform"] == 1
    assert summary.counts_by_kind["DataProduct"] == 1


def test_offering_dedup_merges_across_pillars(seeded_cross_pillar):
    canonical = svc.get_canonical("Offering", "OFF-DMA")
    assert canonical is not None
    assert canonical["canonical_id"] == "OFF-DMA"
    assert canonical["entity_kind"] == "Offering"
    assert canonical["identity"]["offering_name"] == "Data Modernization & AI Platform"
    # Both pillars listed in provenance
    assert set(canonical["source_pillars"]) == {"P1", "P3"}
    # Per-pillar numerics preserved separately
    assert canonical["per_pillar"]["P1"]["total_mapped_subcaps"] == 13
    assert canonical["per_pillar"]["P3"]["total_mapped_subcaps"] == 9


def test_l3_platform_name_divergence_is_flagged(seeded_cross_pillar):
    canonical = svc.get_canonical("L3Platform", "L3-DB-LAKEHOUSE")
    assert canonical is not None
    # Two non-empty different names → divergence flagged
    assert any("name" in f for f in canonical.get("divergence_flags", []))


def test_data_product_with_single_pillar_origin(seeded_cross_pillar):
    canonical = svc.get_canonical("DataProduct", "DP-1.1")
    assert canonical is not None
    assert canonical["source_pillars"] == ["P1"]
    assert canonical["identity"]["module_name"] == "Customer 360 Golden Record"
    assert canonical["divergence_flags"] == []


def test_list_canonical_filters_by_kind(seeded_cross_pillar):
    offerings = svc.list_canonical("Offering")
    assert len(offerings) == 1
    assert offerings[0]["canonical_id"] == "OFF-DMA"


def test_list_canonical_returns_all_kinds_when_unfiltered(seeded_cross_pillar):
    all_rows = svc.list_canonical()
    kinds = {r["entity_kind"] for r in all_rows}
    assert kinds == {"Offering", "L3Platform", "DataProduct"}


def test_rebuild_is_idempotent(seeded_cross_pillar):
    """Running rebuild a second time produces the same canonical rows."""
    before = sorted(svc.list_canonical(), key=lambda r: r["canonical_id"])
    svc.rebuild_canonical_entities()
    after = sorted(svc.list_canonical(), key=lambda r: r["canonical_id"])
    assert len(before) == len(after)
    for b, a in zip(before, after):
        assert b["canonical_id"] == a["canonical_id"]
        assert b["source_pillars"] == a["source_pillars"]
        assert b["identity"] == a["identity"]


def test_summary_records_divergences(seeded_cross_pillar):
    summary = seeded_cross_pillar
    divergence_kinds = {d["entity_kind"] for d in summary.divergences}
    assert "L3Platform" in divergence_kinds


def test_supported_kinds():
    assert set(svc.supported_kinds()) >= {"L3Platform", "Offering", "DataProduct", "AgentforceAgent"}


def test_get_canonical_missing_returns_none(settings_for_tests):
    svc.rebuild_canonical_entities()
    assert svc.get_canonical("Offering", "DOES.NOT.EXIST") is None


def test_canonical_document_schema_version_aliased(seeded_cross_pillar):
    """The persisted row must serialise with the _schema_version alias
    so Firestore migration tooling can find it.
    """
    canonical = svc.get_canonical("Offering", "OFF-DMA")
    assert canonical is not None
    assert canonical.get("_schema_version") == "canonical-entity-v1"
