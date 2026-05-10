"""Batch 8 API surface end-to-end."""


def _seed(client, auth_headers) -> None:
    client.post("/api/sheets/refresh/P1", headers=auth_headers)
    client.post("/api/sows/refresh", headers=auth_headers)
    client.post("/api/stories/refresh", headers=auth_headers)
    client.post("/api/benchmarks/refresh?extrapolate=false", headers=auth_headers)
    client.post("/api/news/refresh", headers=auth_headers)
    client.post("/api/lifecycle/recompute", headers=auth_headers)


def test_chat_post_message(client, auth_headers):
    _seed(client, auth_headers)
    r = client.post(
        "/api/chat/messages",
        json={"message": "Tell me about P1C1.1.1"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["conversation_id"].startswith("chat-")
    assert body["reply"]
    listed = client.get("/api/chat", headers=auth_headers).json()
    assert any(c["conversation_id"] == body["conversation_id"] for c in listed)


def test_chat_empty_message_400(client, auth_headers):
    r = client.post("/api/chat/messages", json={"message": "  "}, headers=auth_headers)
    assert r.status_code == 400


def test_what_if_simulate(client, auth_headers):
    _seed(client, auth_headers)
    r = client.post(
        "/api/what-if/simulate",
        json={"actions": [
            {"kind": "set_lifecycle_state",
             "target": {"sub_cap_id": "P1C1.1.1", "state": "STABLE"}},
        ]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["actions_applied"] == 1


def test_personas_list_and_detail(client, auth_headers):
    _seed(client, auth_headers)
    rows = client.get("/api/personas", headers=auth_headers).json()
    assert rows
    name = rows[0]["name"]
    detail = client.get(f"/api/personas/{name}", headers=auth_headers).json()
    assert detail["persona"] == name


def test_personas_404(client, auth_headers):
    _seed(client, auth_headers)
    r = client.get("/api/personas/NotARealPersona", headers=auth_headers)
    assert r.status_code == 404


def test_notifications_refresh_and_mark_read(client, auth_headers):
    _seed(client, auth_headers)
    # Trigger an audit so there's at least an info notification
    client.post("/api/audit/run", headers=auth_headers)
    refresh = client.post("/api/notifications/refresh", headers=auth_headers).json()
    assert "total_count" in refresh
    items = client.get("/api/notifications", headers=auth_headers).json()
    if items:
        nid = items[0]["id"]
        marked = client.post(f"/api/notifications/{nid}/read", headers=auth_headers).json()
        assert marked["read"] is True
    stats = client.get("/api/notifications/stats", headers=auth_headers).json()
    assert "total" in stats


def test_exports_catalogue_xlsx(client, auth_headers):
    _seed(client, auth_headers)
    r = client.get("/api/exports/catalogue.xlsx", headers=auth_headers)
    assert r.status_code == 200
    assert r.content[:2] == b"PK"
    assert "attachment" in r.headers.get("content-disposition", "")


def test_exports_lifecycle_xlsx(client, auth_headers):
    _seed(client, auth_headers)
    r = client.get("/api/exports/lifecycle.xlsx", headers=auth_headers)
    assert r.status_code == 200
    assert r.content[:2] == b"PK"


def test_eval_datasets_and_run(client, auth_headers):
    _seed(client, auth_headers)
    client.post(
        "/api/digest/generate",
        json={"subvertical": "retail-banking", "period": "2026-Q2", "priority_limit": 3},
        headers=auth_headers,
    )
    datasets = client.get("/api/eval/datasets", headers=auth_headers).json()
    assert datasets
    out = client.post("/api/eval/run", headers=auth_headers).json()
    assert out["runs"]
    runs = client.get("/api/eval/runs", headers=auth_headers).json()
    assert any(r["run_id"] == out["runs"][0]["run_id"] for r in runs)


def test_eval_unknown_dataset_404(client, auth_headers):
    r = client.post(
        "/api/eval/run?dataset_id=does-not-exist", headers=auth_headers,
    )
    assert r.status_code == 404
