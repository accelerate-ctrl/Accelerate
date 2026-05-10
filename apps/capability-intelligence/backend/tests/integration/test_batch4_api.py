"""End-to-end exercise of the Batch 4 API surface."""


def test_news_refresh_endpoint(client, auth_headers):
    r = client.post("/api/news/refresh", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["news_loaded"] >= 2
    assert body["trends_loaded"] >= 2


def test_news_list_filters_by_subcap(client, auth_headers):
    client.post("/api/sheets/refresh/P1", headers=auth_headers)
    client.post("/api/news/refresh", headers=auth_headers)
    r = client.get("/api/news?sub_cap_id=P1C1.1.1", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data, "expected news rows tagged with P1C1.1.1"
    assert "P1C1.1.1" in data[0]["sub_cap_hits"]


def test_loop_run_endpoint_writes_chain(client, auth_headers):
    client.post("/api/sheets/refresh/P1", headers=auth_headers)
    client.post("/api/news/refresh", headers=auth_headers)
    r = client.post(
        "/api/reasoning-chains/run",
        json={"query": "audit subcap", "sub_cap_id": "P1C1.1.1", "model": "gemini-flash"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chain_id"].startswith("chain-")
    assert body["overall"] in ("pass", "warn", "fail")

    chains = client.get("/api/reasoning-chains", headers=auth_headers).json()
    assert any(c["chain_id"] == body["chain_id"] for c in chains)


def test_loop_creates_suggestions_listed_via_api(client, auth_headers):
    client.post("/api/sheets/refresh/P1", headers=auth_headers)
    client.post("/api/news/refresh", headers=auth_headers)
    client.post(
        "/api/reasoning-chains/run",
        json={"query": "audit subcap", "sub_cap_id": "P1C1.1.1", "model": "gemini-flash"},
        headers=auth_headers,
    )
    suggestions = client.get("/api/suggestions?status=pending", headers=auth_headers).json()
    assert suggestions

    # Apply one
    sid = suggestions[0]["id"]
    r = client.post(f"/api/suggestions/{sid}/apply", json={}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "applied"

    # Stats reflect it
    stats = client.get("/api/suggestions/stats", headers=auth_headers).json()
    assert stats["applied"] >= 1


def test_validation_gates_summary_aggregates(client, auth_headers):
    client.post("/api/sheets/refresh/P1", headers=auth_headers)
    client.post("/api/news/refresh", headers=auth_headers)
    client.post(
        "/api/reasoning-chains/run",
        json={"query": "audit", "sub_cap_id": "P1C1.1.1", "model": "gemini-flash"},
        headers=auth_headers,
    )
    summary = client.get("/api/validation-gates/summary", headers=auth_headers).json()
    assert summary["total_runs"] >= 1
    assert "by_gate" in summary
    assert "schema" in summary["by_gate"]


def test_unknown_model_400(client, auth_headers):
    r = client.post(
        "/api/reasoning-chains/run",
        json={"query": "x", "model": "totally-not-a-model"},
        headers=auth_headers,
    )
    assert r.status_code == 400
