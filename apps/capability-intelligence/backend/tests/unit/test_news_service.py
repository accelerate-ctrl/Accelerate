"""News + trends ingest via local seed fixtures."""

from app.services import news_service


def test_refresh_loads_seed_files(settings_for_tests):
    summary = news_service.refresh()
    assert summary.news_loaded >= 2
    assert summary.trends_loaded >= 2
    items = news_service.list_news(limit=10)
    assert any("Wells Fargo" in (i.get("title") or "") for i in items)


def test_news_extracts_subcap_mentions(settings_for_tests):
    # need subcaps loaded for mention extraction to fire
    from app.services import catalogue_service
    catalogue_service.refresh_pillar("P1", by="test")

    news_service.refresh()
    items = news_service.list_news(limit=20, sub_cap_id="P1C1.1.1")
    assert items, "news mentioning P1C1.1.1 should be found"
    assert "P1C1.1.1" in items[0].get("sub_cap_hits", [])


def test_news_idempotent(settings_for_tests):
    a = news_service.refresh()
    b = news_service.refresh()
    assert a.news_loaded == b.news_loaded
    assert a.trends_loaded == b.trends_loaded
