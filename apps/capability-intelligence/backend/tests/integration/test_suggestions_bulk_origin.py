"""Bulk reject + origin filter (Phase 4.3 / IMP-11)."""

import pytest

from app.services import suggestions_service
from app.services.repository import get_repository


@pytest.fixture
def seeded_suggestions(client):
    """Seed 8 pending suggestions from 4 different origins."""
    repo = get_repository()
    origins_and_status = [
        ("loop", "pending"),
        ("loop", "pending"),
        ("news", "pending"),
        ("news", "pending"),
        ("partner", "pending"),
        ("audit", "applied"),  # already applied — bulk should skip
        ("what-if", "pending"),
        ("loop", "rejected"),  # already rejected — bulk should skip
    ]
    for i, (origin, status) in enumerate(origins_and_status):
        sid = f"sug-{i:03d}"
        repo.upsert("suggestions", sid, {
            "id": sid,
            "status": status,
            "origin": origin,
            "sub_cap_id": "P1C1.1.1",
            "kind": "maturity_descriptor_update",
            "title": f"Test suggestion {i}",
            "created_at": f"2026-05-{15+i:02d}T08:00:00Z",
        })
    return client


# ─── Origin filter ────────────────────────────────────────────────────────


def test_list_filters_by_origin(seeded_suggestions, auth_headers):
    r = seeded_suggestions.get(
        "/api/suggestions?origin=news", headers=auth_headers,
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    for row in rows:
        assert row["origin"] == "news"


def test_list_origins_endpoint(seeded_suggestions, auth_headers):
    r = seeded_suggestions.get("/api/suggestions/origins", headers=auth_headers)
    body = r.json()
    assert body["origins"]["loop"] == 3
    assert body["origins"]["news"] == 2
    assert body["origins"]["partner"] == 1
    assert body["origins"]["audit"] == 1
    assert body["origins"]["what-if"] == 1


def test_list_default_no_filter_returns_all(seeded_suggestions, auth_headers):
    r = seeded_suggestions.get("/api/suggestions?limit=20", headers=auth_headers)
    assert len(r.json()) == 8


def test_legacy_suggestions_without_origin_default_to_loop(client, settings_for_tests, auth_headers):
    """Legacy suggestions with no explicit origin field should still
    surface when the user filters by ``loop`` (the historical default)."""
    repo = get_repository()
    repo.upsert("suggestions", "legacy-1", {
        "id": "legacy-1",
        "status": "pending",
        "sub_cap_id": "P1C1.1.1",
        "title": "Legacy",
        "created_at": "2026-05-01T08:00:00Z",
        # No ``origin`` field.
    })
    r = client.get("/api/suggestions?origin=loop", headers=auth_headers)
    rows = r.json()
    assert any(row["id"] == "legacy-1" for row in rows)


# ─── Bulk reject ──────────────────────────────────────────────────────────


def test_bulk_reject_rejects_pending_and_skips_others(seeded_suggestions, auth_headers):
    ids = [f"sug-{i:03d}" for i in range(8)]
    r = seeded_suggestions.post(
        "/api/suggestions/bulk-reject",
        json={"ids": ids, "reason": "low quality batch — manual triage"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    # 6 pending, 1 already-applied, 1 already-rejected → 6 rejected.
    assert body["rejected_count"] == 6
    assert body["skipped_count"] == 2
    assert body["missing_count"] == 0


def test_bulk_reject_persists_reason(seeded_suggestions, auth_headers):
    seeded_suggestions.post(
        "/api/suggestions/bulk-reject",
        json={"ids": ["sug-000"], "reason": "manual triage rationale"},
        headers=auth_headers,
    )
    after = seeded_suggestions.get("/api/suggestions/sug-000", headers=auth_headers).json()
    assert after["status"] == "rejected"
    assert after["reject_reason"] == "manual triage rationale"
    assert after["bulk_rejected"] is True


def test_bulk_reject_empty_reason_rejected(seeded_suggestions, auth_headers):
    r = seeded_suggestions.post(
        "/api/suggestions/bulk-reject",
        json={"ids": ["sug-000"], "reason": ""},
        headers=auth_headers,
    )
    # Pydantic min_length=1 → 422 before the service ever runs.
    assert r.status_code == 422


def test_bulk_reject_empty_ids_rejected(seeded_suggestions, auth_headers):
    r = seeded_suggestions.post(
        "/api/suggestions/bulk-reject",
        json={"ids": [], "reason": "noop"},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_bulk_reject_handles_missing_ids(seeded_suggestions, auth_headers):
    r = seeded_suggestions.post(
        "/api/suggestions/bulk-reject",
        json={"ids": ["does-not-exist-1", "sug-000"], "reason": "x"},
        headers=auth_headers,
    )
    body = r.json()
    assert body["missing_count"] == 1
    assert body["rejected_count"] == 1


def test_bulk_reject_cap_enforced(seeded_suggestions, auth_headers):
    """200 ids is the cap; 201 must 422 to prevent runaway calls."""
    big_list = [f"sug-{i}" for i in range(201)]
    r = seeded_suggestions.post(
        "/api/suggestions/bulk-reject",
        json={"ids": big_list, "reason": "x"},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_bulk_reject_service_layer_directly(settings_for_tests):
    """Direct service call so we cover the non-API path used by the
    monthly cycle's auto-rejection logic."""
    repo = get_repository()
    for i in range(3):
        repo.upsert("suggestions", f"sx-{i}", {
            "id": f"sx-{i}", "status": "pending", "sub_cap_id": "P1C1.1.1",
        })
    out = suggestions_service.bulk_reject(
        ["sx-0", "sx-1", "sx-2"], actor="x@zen.co", reason="batch test",
    )
    assert out["rejected_count"] == 3
    after = [
        repo.get("suggestions", f"sx-{i}")["status"] for i in range(3)
    ]
    assert after == ["rejected"] * 3


def test_bulk_reject_service_empty_reason_raises(settings_for_tests):
    with pytest.raises(ValueError):
        suggestions_service.bulk_reject(["x"], "actor", reason="")
