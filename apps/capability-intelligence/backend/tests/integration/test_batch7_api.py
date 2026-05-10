"""Batch 7 API surface end-to-end: digest + audit + PPTX download."""


def _seed(client, auth_headers) -> None:
    client.post("/api/sheets/refresh/P1", headers=auth_headers)
    client.post("/api/sows/refresh", headers=auth_headers)
    client.post("/api/stories/refresh", headers=auth_headers)
    client.post("/api/benchmarks/refresh?extrapolate=false", headers=auth_headers)
    client.post("/api/news/refresh", headers=auth_headers)
    client.post("/api/lifecycle/recompute", headers=auth_headers)


def test_digest_generate(client, auth_headers):
    _seed(client, auth_headers)
    r = client.post(
        "/api/digest/generate",
        json={"subvertical": "retail-banking", "period": "2026-Q2", "priority_limit": 3},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subvertical"] == "retail-banking"
    assert body["period"] == "2026-Q2"
    assert body["priorities"]
    assert body["digest_id"] == "digest-retail-banking-2026-Q2"


def test_digest_list_filters(client, auth_headers):
    _seed(client, auth_headers)
    client.post(
        "/api/digest/generate",
        json={"subvertical": "retail-banking", "period": "2026-Q2"},
        headers=auth_headers,
    )
    client.post(
        "/api/digest/generate",
        json={"subvertical": "wealth-management", "period": "2026-Q2"},
        headers=auth_headers,
    )
    only_rb = client.get(
        "/api/digest?subvertical=retail-banking", headers=auth_headers,
    ).json()
    assert all(d["subvertical"] == "retail-banking" for d in only_rb)


def test_digest_pptx_download(client, auth_headers):
    _seed(client, auth_headers)
    gen = client.post(
        "/api/digest/generate",
        json={"subvertical": "retail-banking", "period": "2026-Q2"},
        headers=auth_headers,
    ).json()
    digest_id = gen["digest_id"]
    r = client.get(f"/api/digest/{digest_id}/pptx", headers=auth_headers)
    assert r.status_code == 200
    assert r.content[:2] == b"PK"
    assert "attachment" in r.headers.get("content-disposition", "")


def test_digest_404(client, auth_headers):
    r = client.get("/api/digest/digest-does-not-exist", headers=auth_headers)
    assert r.status_code == 404


def test_audit_run(client, auth_headers):
    _seed(client, auth_headers)
    r = client.post("/api/audit/run", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "report_id" in body
    assert "summary" in body
    listed = client.get("/api/audit", headers=auth_headers).json()
    assert any(rep["report_id"] == body["report_id"] for rep in listed)


def test_audit_latest_returns_most_recent(client, auth_headers):
    a = client.post("/api/audit/run", headers=auth_headers).json()
    b = client.post("/api/audit/run", headers=auth_headers).json()
    latest = client.get("/api/audit/latest", headers=auth_headers).json()
    assert latest["report_id"] == b["report_id"]
    assert latest["report_id"] != a["report_id"]


def test_audit_404(client, auth_headers):
    r = client.get("/api/audit/audit-does-not-exist", headers=auth_headers)
    assert r.status_code == 404
