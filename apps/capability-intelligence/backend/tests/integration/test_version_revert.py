"""Version revert tests (Phase 4.5 / App Flow J11)."""

import pytest

from app.services import version_service
from app.services.catalogue_service import COLLECTIONS
from app.services.repository import get_repository


@pytest.fixture(autouse=True)
def _admin_email(monkeypatch):
    """Allow-list the dev test user so admin_dep passes for these tests."""
    monkeypatch.setenv("ADMIN_EMAILS", "test@zennify.com")


@pytest.fixture
def two_versions(client):
    """Snapshot the catalogue twice — once with 3 subcaps, then with
    2 subcaps after deleting one + modifying another."""
    repo = get_repository()
    # Seed initial subcaps.
    repo.upsert(COLLECTIONS["pillars"], "P1", {"pillar_id": "P1", "name": "P1"})
    for sid in ("P1C1.1.1", "P1C2.1.1", "P1C3.1.1"):
        repo.upsert(COLLECTIONS["subcaps"], sid, {
            "sub_cap_id": sid,
            "sub_cap_name": f"Original {sid}",
            "pillar_id": "P1",
            "category_id": sid.split(".")[0],
            "l1_capability": "L1",
            "tier": "T1",
        })
    v_original = version_service.save_version(
        label="v1-original", summary="initial", by="seed",
    )
    # Mutate: delete P1C3.1.1, rename P1C1.1.1.
    repo.delete(COLLECTIONS["subcaps"], "P1C3.1.1")
    repo.upsert(COLLECTIONS["subcaps"], "P1C1.1.1", {
        "sub_cap_id": "P1C1.1.1",
        "sub_cap_name": "Renamed Strategy Doc",
        "pillar_id": "P1",
        "category_id": "P1C1",
        "l1_capability": "L1",
        "tier": "T1",
    })
    v_modified = version_service.save_version(
        label="v2-modified", summary="renamed + deleted", by="seed",
    )
    return client, v_original["version_id"], v_modified["version_id"]


# ─── Service-level revert ──────────────────────────────────────────────────


def test_preview_revert_lists_exact_deltas(two_versions):
    _client, v_original, _v_modified = two_versions
    preview = version_service.preview_revert(v_original)
    # The original had 3 subcaps; current has 2. Reverting would add
    # P1C3.1.1 back and modify P1C1.1.1.
    assert "P1C3.1.1" in preview["added_subcaps"]
    assert any(m["sub_cap_id"] == "P1C1.1.1" for m in preview["modified_subcaps"])
    assert preview["current_subcap_count"] == 2
    assert preview["target_subcap_count"] == 3


def test_revert_restores_subcap_state(two_versions):
    _client, v_original, _v_modified = two_versions
    repo = get_repository()
    out = version_service.revert_to_version(
        v_original, by="admin@zen.co", reason="regression detected",
    )
    assert out["added"] >= 1
    # P1C3.1.1 is back.
    assert repo.get(COLLECTIONS["subcaps"], "P1C3.1.1") is not None
    # P1C1.1.1 is the original name again.
    assert repo.get(COLLECTIONS["subcaps"], "P1C1.1.1")["sub_cap_name"] == "Original P1C1.1.1"


def test_revert_creates_new_current_version(two_versions):
    _client, v_original, _v_modified = two_versions
    out = version_service.revert_to_version(
        v_original, by="admin@zen.co", reason="x",
    )
    new_v = out["new_version_id"]
    assert new_v.startswith("v-revert-")
    fetched = version_service.get_version(new_v)
    assert fetched["is_current"] is True
    assert fetched["is_revert"] is True
    assert fetched["reverted_to"] == v_original


def test_revert_logs_audit_row(two_versions):
    _client, v_original, _v_modified = two_versions
    version_service.revert_to_version(v_original, by="admin@zen.co", reason="audit-test")
    reverts = version_service.list_reverts()
    assert reverts
    assert reverts[0]["target_version_id"] == v_original
    assert reverts[0]["reason"] == "audit-test"
    assert reverts[0]["performed_by"] == "admin@zen.co"


def test_revert_requires_reason(two_versions):
    _client, v_original, _ = two_versions
    with pytest.raises(ValueError):
        version_service.revert_to_version(v_original, by="x", reason="")


def test_revert_unknown_version_raises():
    with pytest.raises(KeyError):
        version_service.revert_to_version("v-does-not-exist", by="x", reason="r")


# ─── API surface ──────────────────────────────────────────────────────────


def test_preview_endpoint_open_to_authenticated_users(two_versions, auth_headers):
    client, v_original, _ = two_versions
    r = client.get(
        f"/api/versions/{v_original}/revert-preview", headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert "added_subcaps" in body
    assert "modified_subcaps" in body


def test_revert_endpoint_requires_admin(two_versions, monkeypatch):
    """A regular user (not in ADMIN_EMAILS) must get 403."""
    client, v_original, _ = two_versions
    # Override admin list so the dev user is NOT admin.
    monkeypatch.setenv("ADMIN_EMAILS", "someone-else@zen.co")
    r = client.post(
        f"/api/versions/{v_original}/revert",
        json={"reason": "x"},
        headers={"Authorization": "Bearer dev-test@zennify.com"},
    )
    assert r.status_code == 403


def test_revert_endpoint_succeeds_for_admin(two_versions, auth_headers):
    client, v_original, _ = two_versions
    r = client.post(
        f"/api/versions/{v_original}/revert",
        json={"reason": "regression in prod"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["new_version_id"].startswith("v-revert-")
    assert body["reason"] == "regression in prod"


def test_revert_endpoint_rejects_empty_reason(two_versions, auth_headers):
    client, v_original, _ = two_versions
    r = client.post(
        f"/api/versions/{v_original}/revert",
        json={"reason": ""},
        headers=auth_headers,
    )
    # Pydantic min_length=1 → 422
    assert r.status_code == 422


def test_revert_endpoint_404_for_unknown_version(client, settings_for_tests, auth_headers):
    r = client.post(
        "/api/versions/v-bogus/revert",
        json={"reason": "x"},
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_reverts_audit_endpoint(two_versions, auth_headers):
    client, v_original, _ = two_versions
    client.post(
        f"/api/versions/{v_original}/revert",
        json={"reason": "audit-endpoint-test"},
        headers=auth_headers,
    )
    r = client.get("/api/versions/_reverts", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["reverts"]
    assert body["reverts"][0]["reason"] == "audit-endpoint-test"


def test_admin_dep_with_no_allow_list_fails_closed(client, two_versions, monkeypatch):
    """A misconfigured deploy (no ADMIN_EMAILS) must return 403, not
    silently allow the action."""
    _client, v_original, _ = two_versions
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    r = client.post(
        f"/api/versions/{v_original}/revert",
        json={"reason": "x"},
        headers={"Authorization": "Bearer dev-test@zennify.com"},
    )
    assert r.status_code == 403
