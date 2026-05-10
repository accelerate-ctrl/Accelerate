"""Batch 6 API surface end-to-end."""


def _seed(client, auth_headers) -> None:
    client.post("/api/sheets/refresh/P1", headers=auth_headers)
    client.post("/api/sows/refresh", headers=auth_headers)
    client.post("/api/stories/refresh", headers=auth_headers)
    client.post("/api/benchmarks/refresh?extrapolate=false", headers=auth_headers)
    client.post("/api/news/refresh", headers=auth_headers)


def test_lifecycle_recompute(client, auth_headers):
    _seed(client, auth_headers)
    r = client.post("/api/lifecycle/recompute", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subcaps_scored"] > 0
    states = client.get("/api/lifecycle/states", headers=auth_headers).json()
    assert sum(states.values()) == body["subcaps_scored"]


def test_lifecycle_filter_by_state(client, auth_headers):
    _seed(client, auth_headers)
    client.post("/api/lifecycle/recompute", headers=auth_headers)
    rising = client.get("/api/lifecycle?state=RISING", headers=auth_headers).json()
    for r in rising:
        assert r["state"] == "RISING"


def test_lifecycle_detail_404(client, auth_headers):
    _seed(client, auth_headers)
    client.post("/api/lifecycle/recompute", headers=auth_headers)
    r = client.get("/api/lifecycle/P9C9.9.9", headers=auth_headers)
    assert r.status_code == 404


def test_vendor_intel_refresh_and_heatmap(client, auth_headers):
    _seed(client, auth_headers)
    refresh = client.post("/api/vendor-intel/refresh", headers=auth_headers).json()
    assert refresh["vendors_loaded"] > 0
    hm = client.get("/api/vendor-intel/heatmap", headers=auth_headers).json()
    assert "vendors" in hm and "cohorts" in hm and "cells" in hm


def test_vendor_intel_adoption_filter(client, auth_headers):
    _seed(client, auth_headers)
    client.post("/api/vendor-intel/refresh", headers=auth_headers)
    rows = client.get(
        "/api/vendor-intel/adoption?cohort_id=us_banks_gsib", headers=auth_headers,
    ).json()
    for r in rows:
        assert r["cohort_id"] == "us_banks_gsib"


def test_client_journey_returns_dma_packet(client, auth_headers):
    _seed(client, auth_headers)
    client.post("/api/lifecycle/recompute", headers=auth_headers)
    client.post("/api/vendor-intel/refresh", headers=auth_headers)

    j = client.get("/api/clients/Wells%20Fargo/journey", headers=auth_headers).json()
    assert j["client_name"] == "Wells Fargo"
    assert j["touched_subcaps"]

    packet = client.get(
        "/api/clients/Wells%20Fargo/dma-packet", headers=auth_headers,
    ).json()
    assert packet["schema_version"] == "dma-handoff-v1"
    assert packet["engagement"]["active"] >= 1


def test_client_journey_404(client, auth_headers):
    _seed(client, auth_headers)
    r = client.get("/api/clients/Imaginary%20Bank/journey", headers=auth_headers)
    assert r.status_code == 404


def test_client_refresh_all_lists_journeys(client, auth_headers):
    _seed(client, auth_headers)
    client.post("/api/lifecycle/recompute", headers=auth_headers)
    client.post("/api/vendor-intel/refresh", headers=auth_headers)
    out = client.post("/api/clients/refresh", headers=auth_headers).json()
    assert out["clients_built"] >= 2
    listed = client.get("/api/clients", headers=auth_headers).json()
    assert listed
