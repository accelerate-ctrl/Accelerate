"""Subcap detail endpoint → ``affected_news`` join (Phase 2.1).

Verifies the API surfaces news items touching a subcap, ordered by
magnitude then recency, with the structured payload preferred over the
legacy flat list and ingest-time fuzzy match."""

import pytest

from app.services import catalogue_service
from app.services.repository import get_repository


@pytest.fixture
def seeded_news(client):
    """Seed P1 fixture + three news items targeting one subcap with
    different magnitudes."""
    catalogue_service.refresh_pillar("P1", by="test")
    repo = get_repository()
    repo.upsert("news_items", "news-high", {
        "id": "news-high",
        "title": "Regulator action on Strategy Definition",
        "source": "occ.gov",
        "url": "https://occ.gov/news/x",
        "published_at": "2026-05-15T08:00:00Z",
        "kind": "news",
        "sub_cap_hits": ["P1C1.1.1"],
        "impact": {
            "summary": "Direct OCC rule",
            "impact_class": "catalogue_extension",
            "affected_subcaps": [
                {"sub_cap_id": "P1C1.1.1", "magnitude": "HIGH", "rationale": "Direct rule"},
            ],
            "affects_subcaps": ["P1C1.1.1"],
            "confidence": 0.9,
        },
    })
    repo.upsert("news_items", "news-med", {
        "id": "news-med",
        "title": "Industry trend touches Strategy Definition",
        "source": "americanbanker.com",
        "url": "https://americanbanker.com/x",
        "published_at": "2026-05-10T08:00:00Z",
        "kind": "news",
        "sub_cap_hits": [],
        "impact": {
            "summary": "Trend coverage",
            "impact_class": "reinforcement",
            "affected_subcaps": [
                {"sub_cap_id": "P1C1.1.1", "magnitude": "MEDIUM", "rationale": "Trend"},
            ],
            "affects_subcaps": ["P1C1.1.1"],
            "confidence": 0.6,
        },
    })
    repo.upsert("news_items", "news-legacy", {
        "id": "news-legacy",
        "title": "Old cached impact (legacy shape)",
        "source": "fdic.gov",
        "url": "https://fdic.gov/news/x",
        "published_at": "2026-04-20T08:00:00Z",
        "kind": "news",
        "sub_cap_hits": [],
        # No structured `affected_subcaps`; only the legacy flat list.
        "impact": {
            "summary": "Legacy item",
            "impact_class": "reinforcement",
            "affects_subcaps": ["P1C1.1.1"],
            "confidence": 0.4,
        },
    })
    # An unrelated news item — must NOT show up in the join.
    repo.upsert("news_items", "news-unrelated", {
        "id": "news-unrelated",
        "title": "Unrelated cyber news",
        "source": "wired.com",
        "url": "https://wired.com/x",
        "published_at": "2026-05-12T08:00:00Z",
        "kind": "news",
        "sub_cap_hits": [],
        "impact": {
            "summary": "irrelevant",
            "impact_class": "no_impact",
            "affected_subcaps": [],
            "affects_subcaps": [],
            "confidence": 0.1,
        },
    })
    return client


def test_affected_news_surfaces_in_subcap_detail(seeded_news, auth_headers):
    r = seeded_news.get("/api/catalogue/subcaps/P1C1.1.1", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    news = body.get("affected_news") or []
    assert len(news) == 3
    # Sorted by magnitude (HIGH > MEDIUM > LOW); the legacy item drops
    # to LOW because it lacks an explicit magnitude.
    assert [n["magnitude"] for n in news] == ["HIGH", "MEDIUM", "LOW"]
    assert news[0]["news_id"] == "news-high"
    assert news[0]["rationale"] == "Direct rule"


def test_unrelated_news_excluded(seeded_news, auth_headers):
    r = seeded_news.get("/api/catalogue/subcaps/P1C1.1.1", headers=auth_headers)
    news_ids = {n["news_id"] for n in r.json().get("affected_news", [])}
    assert "news-unrelated" not in news_ids


def test_fuzzy_sub_cap_hits_still_counted(seeded_news, auth_headers):
    """News items lacking any impact block but with a ``sub_cap_hits``
    entry from ingest-time fuzzy match should still surface with LOW
    magnitude — they represent unscored items in the queue.
    """
    repo = get_repository()
    repo.upsert("news_items", "news-fuzzy", {
        "id": "news-fuzzy",
        "title": "Fuzzy match no LLM scoring yet",
        "source": "x.com",
        "url": "https://x.com/y",
        "published_at": "2026-05-17T08:00:00Z",
        "kind": "news",
        "sub_cap_hits": ["P1C1.1.1"],
    })
    r = seeded_news.get("/api/catalogue/subcaps/P1C1.1.1", headers=auth_headers)
    news_ids = {n["news_id"] for n in r.json().get("affected_news", [])}
    assert "news-fuzzy" in news_ids
