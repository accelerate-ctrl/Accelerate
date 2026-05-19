"""Tests for the evidence-driven vendor × subcap heatmap (Phase 2.3).

Per TRD §11 / Schema §5.5, the vendor heatmap must be derived from real
signals — vendor_events joined to news_items.impact.affected_subcaps —
not the fixture-based vendor×cohort adoption matrix. These tests cover
that join.
"""

import pytest

from app.services import vendor_intel_service as svc
from app.services.repository import get_repository


@pytest.fixture
def seeded_evidence(settings_for_tests):
    """Seed news items with impact + structured affected_subcaps and
    the vendor_events that point to them.
    """
    repo = get_repository()

    # News item with HIGH-magnitude impact on P1C3.5.2 affecting Salesforce.
    repo.upsert("news_items", "news-001", {
        "id": "news-001",
        "title": "Salesforce ships open banking connector",
        "source": "salesforce.com",
        "url": "https://salesforce.com/news/open-banking",
        "published_at": "2026-05-15T08:00:00Z",
        "impact": {
            "impact_class": "catalogue_extension",
            "affected_subcaps": [
                {"sub_cap_id": "P1C3.5.2", "magnitude": "HIGH", "rationale": "Direct"},
                {"sub_cap_id": "P1C1.1.1", "magnitude": "MEDIUM", "rationale": "Adjacent"},
            ],
            "affects_subcaps": ["P1C3.5.2", "P1C1.1.1"],
        },
    })
    repo.upsert("news_items", "news-002", {
        "id": "news-002",
        "title": "nCino announces digital lending platform",
        "source": "ncino.com",
        "url": "https://ncino.com/x",
        "published_at": "2026-05-12T08:00:00Z",
        "impact": {
            "impact_class": "reinforcement",
            # Only legacy flat list — exercises the back-compat path.
            "affects_subcaps": ["P1C2.3.1"],
        },
    })
    # Vendor events referencing these news items by the standard
    # ``evt-{vendor_id}-{news_id}`` id pattern.
    repo.upsert("vendor_events", "evt-salesforce-news-001", {
        "id": "evt-salesforce-news-001",
        "vendor_id": "salesforce",
        "vendor_name": "Salesforce",
        "kind": "news",
        "title": "Salesforce ships open banking connector",
        "published_at": "2026-05-15T08:00:00Z",
    })
    repo.upsert("vendor_events", "evt-ncino-news-002", {
        "id": "evt-ncino-news-002",
        "vendor_id": "ncino",
        "vendor_name": "nCino",
        "kind": "news",
        "title": "nCino lending platform",
        "published_at": "2026-05-12T08:00:00Z",
    })
    # An event without a matching news item — must be silently skipped.
    repo.upsert("vendor_events", "evt-orphan-news-999", {
        "id": "evt-orphan-news-999",
        "vendor_id": "orphan",
        "vendor_name": "Orphan",
        "kind": "news",
        "published_at": "2026-05-10T08:00:00Z",
    })
    return repo


def test_heatmap_returns_envelope(seeded_evidence):
    out = svc.subcap_evidence_heatmap()
    assert "vendors" in out
    assert "subcaps" in out
    assert "cells" in out
    assert out["total_events_joined"] >= 3  # 2 from sf-news-001 + 1 from ncino


def test_high_magnitude_propagates_through_join(seeded_evidence):
    out = svc.subcap_evidence_heatmap()
    sf_open_banking = next(
        c for c in out["cells"]
        if c["vendor_id"] == "salesforce" and c["sub_cap_id"] == "P1C3.5.2"
    )
    assert sf_open_banking["magnitude"] == "HIGH"
    assert sf_open_banking["event_count"] >= 1


def test_medium_magnitude_preserved(seeded_evidence):
    out = svc.subcap_evidence_heatmap()
    sf_strategy = next(
        c for c in out["cells"]
        if c["vendor_id"] == "salesforce" and c["sub_cap_id"] == "P1C1.1.1"
    )
    assert sf_strategy["magnitude"] == "MEDIUM"


def test_legacy_flat_list_synthesises_low_magnitude(seeded_evidence):
    """vendor_event referencing a news item with only the legacy
    flat affects_subcaps list still produces a cell at LOW magnitude.
    """
    out = svc.subcap_evidence_heatmap()
    ncino_cell = next(
        c for c in out["cells"]
        if c["vendor_id"] == "ncino" and c["sub_cap_id"] == "P1C2.3.1"
    )
    assert ncino_cell["magnitude"] == "LOW"


def test_orphan_event_is_skipped(seeded_evidence):
    """An event whose news_id can't be resolved must not produce a cell."""
    out = svc.subcap_evidence_heatmap()
    assert all(c["vendor_id"] != "orphan" for c in out["cells"])


def test_latest_event_timestamp_tracked(seeded_evidence):
    out = svc.subcap_evidence_heatmap()
    sf_open_banking = next(
        c for c in out["cells"]
        if c["vendor_id"] == "salesforce" and c["sub_cap_id"] == "P1C3.5.2"
    )
    assert sf_open_banking["latest_event"] == "2026-05-15T08:00:00Z"


def test_aggregates_multiple_events_per_cell(seeded_evidence):
    """Two events for the same (vendor, subcap) pair should accumulate
    the event_count and keep the highest magnitude.
    """
    repo = get_repository()
    # Seed a second LOW-magnitude event for salesforce × P1C3.5.2.
    repo.upsert("news_items", "news-003", {
        "id": "news-003",
        "title": "Salesforce minor update",
        "impact": {
            "impact_class": "reinforcement",
            "affected_subcaps": [
                {"sub_cap_id": "P1C3.5.2", "magnitude": "LOW", "rationale": "x"},
            ],
        },
        "published_at": "2026-05-20T08:00:00Z",
    })
    repo.upsert("vendor_events", "evt-salesforce-news-003", {
        "id": "evt-salesforce-news-003",
        "vendor_id": "salesforce",
        "vendor_name": "Salesforce",
        "kind": "news",
        "published_at": "2026-05-20T08:00:00Z",
    })
    out = svc.subcap_evidence_heatmap()
    sf_open_banking = next(
        c for c in out["cells"]
        if c["vendor_id"] == "salesforce" and c["sub_cap_id"] == "P1C3.5.2"
    )
    assert sf_open_banking["event_count"] == 2
    # HIGH stays the winner
    assert sf_open_banking["magnitude"] == "HIGH"
    # latest_event reflects the new entry
    assert sf_open_banking["latest_event"] == "2026-05-20T08:00:00Z"


def test_vendor_with_hyphenated_id(seeded_evidence):
    """Vendor ids containing dashes (e.g. ``salesforce-data-cloud``)
    must still resolve the news_id correctly via the join helper.
    """
    repo = get_repository()
    repo.upsert("news_items", "news-zzz", {
        "id": "news-zzz",
        "title": "x",
        "impact": {
            "impact_class": "reinforcement",
            "affected_subcaps": [
                {"sub_cap_id": "P1C9.9.9", "magnitude": "HIGH", "rationale": "x"},
            ],
        },
    })
    repo.upsert("vendor_events", "evt-salesforce-data-cloud-news-zzz", {
        "id": "evt-salesforce-data-cloud-news-zzz",
        "vendor_id": "salesforce-data-cloud",
        "vendor_name": "Salesforce Data Cloud",
        "kind": "news",
    })
    out = svc.subcap_evidence_heatmap()
    cell = next(
        (c for c in out["cells"] if c["vendor_id"] == "salesforce-data-cloud"),
        None,
    )
    assert cell is not None
    assert cell["sub_cap_id"] == "P1C9.9.9"
    assert cell["magnitude"] == "HIGH"


def test_empty_repository_returns_empty_envelope(settings_for_tests):
    out = svc.subcap_evidence_heatmap()
    assert out["vendors"] == []
    assert out["subcaps"] == []
    assert out["cells"] == []
    assert out["total_events_joined"] == 0
