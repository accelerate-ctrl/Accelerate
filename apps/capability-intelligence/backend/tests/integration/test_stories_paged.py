"""Paginated story listings (IMP-3 / Phase 2.2)."""

import pytest

from app.services import stories_service
from app.services.repository import get_repository


CANONICAL_COLL = stories_service.CANONICAL_COLL
JIRA_COLL = stories_service.JIRA_COLL


@pytest.fixture
def seeded_stories(client):
    """Seed 250 canonical + 50 jira rows so pagination has work to do."""
    repo = get_repository()
    for i in range(250):
        key = f"P1C1.1.{(i % 5) + 1}.S{i}"
        repo.upsert(CANONICAL_COLL, key, {
            "story_key": key,
            "sub_cap_id": f"P1C1.1.{(i % 5) + 1}",
            "summary": (
                f"Story {i} about {'open banking' if i % 7 == 0 else 'governance'}"
            ),
            "confidence_level": "HIGH" if i % 3 == 0 else "MEDIUM",
        })
    for i in range(50):
        key = f"JIRA-{i}"
        repo.upsert(JIRA_COLL, key, {
            "story_key": key,
            "sub_cap_id": "P1C2.1.1" if i % 2 == 0 else "P1C1.1.1",
            "summary": f"Jira ticket {i}",
            "status": "Done",
            "issue_type": "Story",
        })
    return client


def test_canonical_paged_returns_envelope(seeded_stories, auth_headers):
    r = seeded_stories.get(
        "/api/stories/canonical/paged?limit=50",
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 250
    assert body["offset"] == 0
    assert body["limit"] == 50
    assert len(body["rows"]) == 50


def test_canonical_paged_offset_skips(seeded_stories, auth_headers):
    r = seeded_stories.get(
        "/api/stories/canonical/paged?offset=200&limit=100",
        headers=auth_headers,
    )
    body = r.json()
    # Only 50 rows remain at offset 200 (total 250)
    assert len(body["rows"]) == 50
    assert body["offset"] == 200


def test_canonical_paged_filter_q(seeded_stories, auth_headers):
    """Query filter operates across the full corpus, not just the page."""
    r = seeded_stories.get(
        "/api/stories/canonical/paged?q=open%20banking&limit=200",
        headers=auth_headers,
    )
    body = r.json()
    # Roughly 1 in 7 rows match.
    assert body["total"] >= 30
    for row in body["rows"]:
        assert "open banking" in row["summary"]


def test_canonical_paged_filter_by_subcap(seeded_stories, auth_headers):
    r = seeded_stories.get(
        "/api/stories/canonical/paged?sub_cap_id=P1C1.1.1&limit=200",
        headers=auth_headers,
    )
    body = r.json()
    assert body["total"] == 50  # exactly 1/5 of 250
    for row in body["rows"]:
        assert row["sub_cap_id"] == "P1C1.1.1"


def test_jira_paged(seeded_stories, auth_headers):
    r = seeded_stories.get(
        "/api/stories/jira/paged?limit=20",
        headers=auth_headers,
    )
    body = r.json()
    assert body["total"] == 50
    assert len(body["rows"]) == 20


def test_paged_empty_corpus_returns_zero(client, settings_for_tests, auth_headers):
    r = client.get("/api/stories/canonical/paged?limit=50", headers=auth_headers)
    body = r.json()
    assert body["total"] == 0
    assert body["rows"] == []


def test_paged_query_with_subcap_filter_intersects(seeded_stories, auth_headers):
    """Subcap filter + text filter compose correctly."""
    r = seeded_stories.get(
        "/api/stories/canonical/paged?sub_cap_id=P1C1.1.1&q=governance&limit=200",
        headers=auth_headers,
    )
    body = r.json()
    for row in body["rows"]:
        assert row["sub_cap_id"] == "P1C1.1.1"
        assert "governance" in row["summary"]
