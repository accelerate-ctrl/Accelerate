"""KG Layer B + snapshot API integration tests (Phase 3.3 + 3.2)."""

import pytest

from app.services import graph_layer_b_proposer as lb
from app.services.catalogue_service import COLLECTIONS
from app.services.repository import get_repository


@pytest.fixture
def seeded_pending(client):
    """Seed a small catalogue + cross-pillar story corpus, run the
    proposer once so the pending-edges collection has rows for the
    inbox endpoint to surface.
    """
    repo = get_repository()
    for sid in ("P1C1.1.1", "P2C4.1.1", "P3C2.1.1"):
        repo.upsert(COLLECTIONS["subcaps"], sid, {
            "sub_cap_id": sid, "sub_cap_name": sid,
            "pillar_id": sid[:2], "category_id": "C1", "l1_capability": "L1",
        })
    # Cross-pillar stories with co-occurrence ≥ 2 → CROSS_PILLAR_DEPENDENCY.
    for i in range(3):
        repo.upsert("cross_pillar_stories", f"K-{i}", {
            "story_key": f"K-{i}",
            "origin_sub_cap_id": "P2C4.1.1",
            "linked_sub_caps": ["P1C1.1.1"],
            "themes": ["strategy"],
        })
    lb.propose_edges()
    return client


# ─── List / runs endpoints ─────────────────────────────────────────────────


def test_layer_b_pending_list(seeded_pending, auth_headers):
    r = seeded_pending.get("/api/graph/layer-b/pending", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    assert all(row.get("status") == "pending" for row in rows)


def test_layer_b_pending_filter_by_kind(seeded_pending, auth_headers):
    r = seeded_pending.get(
        "/api/graph/layer-b/pending?kind=CROSS_PILLAR_DEPENDENCY",
        headers=auth_headers,
    )
    assert r.status_code == 200
    rows = r.json()
    assert rows
    for row in rows:
        assert row["kind"] == "CROSS_PILLAR_DEPENDENCY"


def test_layer_b_runs_endpoint(seeded_pending, auth_headers):
    r = seeded_pending.get("/api/graph/layer-b/runs", headers=auth_headers)
    assert r.status_code == 200
    runs = r.json()
    assert runs
    assert runs[0].get("edges_proposed", 0) >= 1


def test_layer_b_propose_endpoint_runs_on_demand(client, settings_for_tests, auth_headers):
    """The on-demand POST runs the proposer with operator-supplied
    thresholds and returns the run summary."""
    repo = get_repository()
    for sid in ("S1", "S2"):
        repo.upsert(COLLECTIONS["subcaps"], sid, {
            "sub_cap_id": sid, "sub_cap_name": sid,
            "pillar_id": "P1", "category_id": "C1", "l1_capability": "L1",
        })
    for i in range(3):
        repo.upsert("cross_pillar_stories", f"K-{i}", {
            "story_key": f"K-{i}",
            "origin_sub_cap_id": "S1",
            "linked_sub_caps": ["S2"],
        })
    r = client.post(
        "/api/graph/layer-b/propose",
        json={"cosine_threshold": 0.9, "min_cross_pillar_stories": 2},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"]
    assert body["edges_proposed"] >= 1


# ─── Disposition state machine ────────────────────────────────────────────


def test_approve_pending_edge(seeded_pending, auth_headers):
    pending = seeded_pending.get(
        "/api/graph/layer-b/pending", headers=auth_headers,
    ).json()
    edge_id = pending[0]["edge_id"]
    r = seeded_pending.post(
        f"/api/graph/layer-b/{edge_id}/approve",
        json={"note": "looks correct"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    # No longer in the open list.
    listed = seeded_pending.get(
        "/api/graph/layer-b/pending", headers=auth_headers,
    ).json()
    assert all(p["edge_id"] != edge_id for p in listed)


def test_reject_requires_reason(seeded_pending, auth_headers):
    pending = seeded_pending.get(
        "/api/graph/layer-b/pending", headers=auth_headers,
    ).json()
    edge_id = pending[0]["edge_id"]
    # Empty reason → 422 from Pydantic min_length=1.
    r = seeded_pending.post(
        f"/api/graph/layer-b/{edge_id}/reject",
        json={"reason": ""},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_reject_with_reason(seeded_pending, auth_headers):
    pending = seeded_pending.get(
        "/api/graph/layer-b/pending", headers=auth_headers,
    ).json()
    edge_id = pending[0]["edge_id"]
    r = seeded_pending.post(
        f"/api/graph/layer-b/{edge_id}/reject",
        json={"reason": "duplicate of existing edge"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    assert body["disposition_note"] == "duplicate of existing edge"


def test_defer_keeps_edge_pending_internally(seeded_pending, auth_headers):
    """Defer transitions the edge to ``deferred`` status — the inbox
    list filters those out, but the underlying row is preserved with
    the new status."""
    pending = seeded_pending.get(
        "/api/graph/layer-b/pending", headers=auth_headers,
    ).json()
    edge_id = pending[0]["edge_id"]
    r = seeded_pending.post(
        f"/api/graph/layer-b/{edge_id}/defer",
        json={"note": "come back next quarter"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "deferred"


def test_404_for_unknown_edge(client, settings_for_tests, auth_headers):
    r = client.post(
        "/api/graph/layer-b/edge-does-not-exist/approve",
        json={},
        headers=auth_headers,
    )
    assert r.status_code == 404


# ─── Snapshot state ───────────────────────────────────────────────────────


def test_snapshot_state_empty(client, settings_for_tests, auth_headers):
    r = client.get("/api/graph/snapshot/state", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"snapshot_id": None}


def test_snapshot_state_after_save(client, settings_for_tests, auth_headers):
    from app.services import graph_service, graph_storage
    graph_service.invalidate_cache()
    g = graph_service.build_graph()
    graph_storage.save_snapshot(g)
    r = client.get("/api/graph/snapshot/state", headers=auth_headers)
    body = r.json()
    assert body["snapshot_id"]
    assert body["n_shards"] >= 1
    assert body["node_count"] >= 0
