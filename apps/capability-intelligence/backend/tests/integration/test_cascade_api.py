"""Cascade API endpoint integration tests."""

import pytest

from app.services.catalogue_service import COLLECTIONS
from app.services.repository import get_repository


@pytest.fixture
def seeded(settings_for_tests):
    repo = get_repository()
    sub_cap_id = "P1C2.2.2"
    repo.upsert(COLLECTIONS["subcaps"], sub_cap_id, {
        "sub_cap_id": sub_cap_id,
        "sub_cap_name": "API Test",
        "pillar_id": "P1",
        "category_id": "C2",
        "l1_capability": "L1",
        "zennify_status": "Active",
    })
    for i in range(2):
        repo.upsert(COLLECTIONS["stories"], f"{sub_cap_id}.S{i+1}", {
            "story_key": f"{sub_cap_id}.S{i+1}",
            "sub_cap_id": sub_cap_id,
        })
    return sub_cap_id


def test_preview_returns_report(client, seeded):
    r = client.get(f"/api/cascade/preview/{seeded}")
    assert r.status_code == 200
    body = r.json()
    assert body["sub_cap_id"] == seeded
    assert body["applied"] is False
    assert body["total_rows_affected"] >= 2  # 2 stories
    assert body["targets"]


def test_preview_404_for_unknown(client, settings_for_tests):
    r = client.get("/api/cascade/preview/DOES.NOT.EXIST")
    assert r.status_code == 404


def test_apply_requires_reason(client, seeded):
    r = client.post(f"/api/cascade/apply/{seeded}", json={"to_status": "Inactive"})
    # Pydantic will reject the body (reason missing) with 422
    assert r.status_code == 422


def test_apply_empty_reason_is_rejected(client, seeded):
    r = client.post(
        f"/api/cascade/apply/{seeded}",
        json={"to_status": "Inactive", "reason": ""},
    )
    # min_length=1 → 422
    assert r.status_code == 422


def test_apply_succeeds_with_reason(client, seeded):
    r = client.post(
        f"/api/cascade/apply/{seeded}",
        json={"to_status": "Inactive", "reason": "API integration test"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] is True
    assert body["reason"] == "API integration test"
    assert body["run_id"]
    # Side effects persisted
    repo = get_repository()
    sub = repo.get(COLLECTIONS["subcaps"], seeded)
    assert sub["zennify_status"] == "Inactive"


def test_runs_endpoint_lists_history(client, seeded):
    client.post(
        f"/api/cascade/apply/{seeded}",
        json={"to_status": "Inactive", "reason": "first toggle"},
    )
    r = client.get("/api/cascade/runs?limit=10")
    assert r.status_code == 200
    runs = r.json()["runs"]
    assert any(run["sub_cap_id"] == seeded for run in runs)
