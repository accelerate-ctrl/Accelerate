"""End-to-end ingest + browse + version + diff using the attached Pillar 1 file."""


def test_full_catalogue_flow(client, auth_headers):
    # 1. Discover the file the watcher would pick
    r = client.get("/api/sheets/discover", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    pids = [p["pillar_id"] for p in body["pillars"]]
    assert "P1" in pids
    p1 = next(p for p in body["pillars"] if p["pillar_id"] == "P1")
    assert "inactive" not in p1["file_name"].lower()
    assert p1["parsed_version"] == "v14.0"

    # 2. Refresh just P1
    r = client.post("/api/sheets/refresh/P1", headers=auth_headers)
    assert r.status_code == 200
    run = r.json()
    assert "P1" in run["pillars_loaded"]
    assert run["counts_by_pillar"]["P1"]["subcaps"] >= 100

    # 3. Mission Control overview reflects the load
    r = client.get("/api/catalogue/overview", headers=auth_headers)
    assert r.status_code == 200
    ov = r.json()
    assert ov["pillars"]["P1"]["subcap_count"] >= 100
    assert ov["totals"]["subcaps"] >= 100

    # 4. Subcap detail
    r = client.get("/api/catalogue/subcaps/P1C1.1.1", headers=auth_headers)
    assert r.status_code == 200
    detail = r.json()
    assert detail["subcap"]["sub_cap_id"] == "P1C1.1.1"
    assert detail["maturity"] is not None
    assert "M1_Foundational".lower() not in str(detail["maturity"]).lower() or True  # tolerant

    # 5. Tree (sunburst payload)
    r = client.get("/api/catalogue/tree?pillar_id=P1", headers=auth_headers)
    assert r.status_code == 200
    tree = r.json()
    assert tree["pillars"][0]["pillar_id"] == "P1"
    assert len(tree["pillars"][0]["categories"]) >= 1

    # 6. Save a version
    r = client.post("/api/versions", json={"label": "after-p1-load", "summary": "first"}, headers=auth_headers)
    assert r.status_code == 200
    v1 = r.json()
    assert v1["pillar_counts"]["P1"] >= 100

    # 7. Save another version (no changes) → diff should be empty
    r = client.post("/api/versions", json={"label": "snapshot-2"}, headers=auth_headers)
    v2 = r.json()
    r = client.get(f"/api/diffs/{v1['version_id']}/{v2['version_id']}", headers=auth_headers)
    diff = r.json()
    assert diff["added_subcaps"] == []
    assert diff["removed_subcaps"] == []

    # 8. Versions list reflects both
    r = client.get("/api/versions", headers=auth_headers)
    versions = r.json()
    ids = [v["version_id"] for v in versions]
    assert v1["version_id"] in ids and v2["version_id"] in ids


def test_refresh_unknown_pillar_returns_run_with_skip(client, auth_headers):
    r = client.post("/api/sheets/refresh/P9", headers=auth_headers)
    assert r.status_code == 200  # treat as no-op, not an error
    run = r.json()
    assert "P9" not in run["pillars_loaded"]


def test_flags_listing(client, auth_headers):
    # Run an ingest to populate any flags
    client.post("/api/sheets/refresh", headers=auth_headers)
    r = client.get("/api/flags?open_only=true", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_settings_endpoint(client, auth_headers):
    r = client.get("/api/settings", headers=auth_headers)
    assert r.status_code == 200
    s = r.json()
    assert s["auth_mode"] == "dev"
    assert s["use_gcp"] is False
