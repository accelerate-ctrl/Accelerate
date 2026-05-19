"""Change Flags Inbox — J5 approval-gate endpoint tests."""

import pytest

from app.services.catalogue_service import COLLECTIONS, _make_flag
from app.services.repository import get_repository


@pytest.fixture
def seeded_flags(settings_for_tests):
    """Stage two open flags with different kinds + severities so the
    filter chips exercise meaningfully."""
    repo = get_repository()
    f1 = _make_flag(
        "SCHEMA_INCOMPLETE", "HIGH", "pillar", "P1",
        "v7.0 schema gap", "missing 17_Toggle_Control_Panel",
    )
    f2 = _make_flag(
        "AI_PROPOSED_EDGE", "MEDIUM", "subcap", "P1C1.1.1",
        "Layer-B edge proposal", "SEMANTICALLY_SIMILAR with 0.91 cosine",
    )
    repo.upsert(COLLECTIONS["flags"], f1["flag_id"], f1)
    repo.upsert(COLLECTIONS["flags"], f2["flag_id"], f2)
    return [f1, f2]


def test_list_flags_returns_open(client, seeded_flags, auth_headers):
    r = client.get("/api/flags", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 2


def test_list_flags_filter_by_severity(client, seeded_flags, auth_headers):
    r = client.get("/api/flags?severity=HIGH", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()
    assert all((row.get("severity") or "").upper() == "HIGH" for row in rows)


def test_list_flags_filter_by_kind(client, seeded_flags, auth_headers):
    r = client.get(
        "/api/flags?kind=AI_PROPOSED_EDGE",
        headers=auth_headers,
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    assert all(row.get("kind") == "AI_PROPOSED_EDGE" for row in rows)


def test_kinds_summary(client, seeded_flags, auth_headers):
    r = client.get("/api/flags/_kinds", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "kinds" in body and "severities" in body
    assert body["kinds"].get("SCHEMA_INCOMPLETE", 0) >= 1
    assert body["severities"].get("HIGH", 0) >= 1


def test_approve_resolves_flag(client, seeded_flags, auth_headers):
    flag_id = seeded_flags[0]["flag_id"]
    r = client.post(
        f"/api/flags/{flag_id}/approve",
        json={"note": "looked good"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["disposition"] == "approved"
    assert body["resolved_at"]
    assert body["disposition_by"]
    # No longer in the open list
    open_rows = client.get("/api/flags?open_only=true", headers=auth_headers).json()
    assert flag_id not in {x["flag_id"] for x in open_rows}


def test_reject_requires_reason(client, seeded_flags, auth_headers):
    flag_id = seeded_flags[0]["flag_id"]
    r = client.post(
        f"/api/flags/{flag_id}/reject",
        json={"reason": ""},
        headers=auth_headers,
    )
    # Pydantic min_length=1 → 422
    assert r.status_code == 422


def test_reject_with_reason(client, seeded_flags, auth_headers):
    flag_id = seeded_flags[1]["flag_id"]
    r = client.post(
        f"/api/flags/{flag_id}/reject",
        json={"reason": "duplicate of existing edge"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["disposition"] == "rejected"
    assert body["resolution_note"] == "duplicate of existing edge"


def test_defer_keeps_flag_open(client, seeded_flags, auth_headers):
    flag_id = seeded_flags[0]["flag_id"]
    r = client.post(
        f"/api/flags/{flag_id}/defer",
        json={"note": "come back next quarter"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["disposition"] == "deferred"
    assert body.get("deferred_until")
    # Still open
    open_rows = client.get("/api/flags?open_only=true", headers=auth_headers).json()
    assert flag_id in {x["flag_id"] for x in open_rows}


def test_legacy_resolve_endpoint_still_works(client, seeded_flags, auth_headers):
    flag_id = seeded_flags[0]["flag_id"]
    r = client.post(
        f"/api/flags/{flag_id}/resolve",
        json={"note": "ok"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["disposition"] == "approved"


def test_404_for_unknown_flag(client, settings_for_tests, auth_headers):
    r = client.post(
        "/api/flags/does-not-exist/approve",
        json={},
        headers=auth_headers,
    )
    assert r.status_code == 404
