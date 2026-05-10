"""Benchmarks API end-to-end."""


def test_refresh_endpoint(client, auth_headers):
    r = client.post("/api/benchmarks/refresh?extrapolate=false", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["observations_total"] >= 8
    assert body["distributions_total"] >= 1
    assert body["extrapolations_total"] == 0


def test_list_distributions_filtering(client, auth_headers):
    client.post("/api/benchmarks/refresh?extrapolate=false", headers=auth_headers)

    all_dists = client.get("/api/benchmarks", headers=auth_headers).json()
    assert all_dists

    only_tech = client.get(
        "/api/benchmarks?metric_id=tech_spend_pct_revenue", headers=auth_headers
    ).json()
    assert all(d["metric_id"] == "tech_spend_pct_revenue" for d in only_tech)


def test_subcap_filter_uses_metric_subcap_mappings(client, auth_headers):
    client.post("/api/benchmarks/refresh?extrapolate=false", headers=auth_headers)
    r = client.get("/api/benchmarks?sub_cap_id=P1C2.3.5", headers=auth_headers).json()
    assert r
    metric_ids = {d["metric_id"] for d in r}
    assert "tech_spend_pct_revenue" in metric_ids


def test_cohorts_metrics_sources_endpoints(client, auth_headers):
    client.post("/api/benchmarks/refresh?extrapolate=false", headers=auth_headers)

    cohorts = client.get("/api/benchmarks/cohorts", headers=auth_headers).json()
    assert any(c["cohort_id"] == "us_banks_gsib" for c in cohorts)

    metrics = client.get("/api/benchmarks/metrics", headers=auth_headers).json()
    assert any(m["metric_id"] == "tech_spend_pct_revenue" for m in metrics)

    srcs = client.get("/api/benchmarks/sources", headers=auth_headers).json()
    assert srcs


def test_distribution_detail_404(client, auth_headers):
    r = client.get("/api/benchmarks/dist-does-not-exist", headers=auth_headers)
    assert r.status_code == 404


def test_extrapolation_run_records_chain_id(client, auth_headers):
    r = client.post("/api/benchmarks/refresh?extrapolate=true", headers=auth_headers).json()
    assert r["extrapolations_total"] >= 1
    obs = client.get(
        "/api/benchmarks/observations?metric_id=tech_spend_pct_revenue",
        headers=auth_headers,
    ).json()
    extrapolated = [o for o in obs if o.get("is_extrapolated")]
    assert extrapolated
    assert extrapolated[0]["chain_id"].startswith("chain-")
