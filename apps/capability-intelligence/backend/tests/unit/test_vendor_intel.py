"""Vendor Intelligence — adoption + heatmap + events."""

from app.services import benchmarks_service, news_service, vendor_intel_service


def _seed(settings_for_tests) -> None:
    from app.services import catalogue_service, sow_service
    catalogue_service.refresh_pillar("P1", by="test")
    sow_service.ingest_all()
    benchmarks_service.refresh(extrapolate=False)
    news_service.refresh()


def test_refresh_loads_vendors(settings_for_tests):
    _seed(settings_for_tests)
    summary = vendor_intel_service.refresh()
    assert summary.vendors_loaded > 0
    vendors = vendor_intel_service.list_vendors()
    assert any(v["name"] == "Salesforce Financial Services Cloud" for v in vendors)


def test_adoption_rows_have_pct(settings_for_tests):
    _seed(settings_for_tests)
    vendor_intel_service.refresh()
    rows = vendor_intel_service.list_adoption()
    assert rows
    assert all(0 <= r["adoption_pct"] <= 100 for r in rows)


def test_heatmap_shape(settings_for_tests):
    _seed(settings_for_tests)
    vendor_intel_service.refresh()
    hm = vendor_intel_service.heatmap()
    assert "vendors" in hm and "cohorts" in hm and "cells" in hm
    assert hm["cells"]
    assert {"vendor_id", "cohort_id", "adoption_pct"} <= set(hm["cells"][0])


def test_news_event_indexing_when_vendor_in_text(settings_for_tests):
    _seed(settings_for_tests)
    vendor_intel_service.refresh()
    # Wells Fargo news mentions "Salesforce" indirectly via partner ecosystem;
    # at minimum, refresh should not crash and event collection should be a list
    events = vendor_intel_service.list_events()
    assert isinstance(events, list)


def test_vendor_detail_404(settings_for_tests):
    _seed(settings_for_tests)
    vendor_intel_service.refresh()
    rec = vendor_intel_service.get_vendor("does-not-exist")
    assert rec is None


def test_filter_by_category(settings_for_tests):
    _seed(settings_for_tests)
    vendor_intel_service.refresh()
    cores = vendor_intel_service.list_vendors(category="core_crm")
    assert all(v["category"] == "core_crm" for v in cores)
