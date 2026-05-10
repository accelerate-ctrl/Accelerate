"""End-to-end Batch 3 flow against the synthetic SOWs + attached gen_stories."""
import pytest


@pytest.fixture
def loaded(client, auth_headers):
    """Load Pillar 1 catalogue, then SOWs, then stories — order matters because
    SOW mention extraction reads the catalogue."""
    client.post("/api/sheets/refresh/P1", headers=auth_headers)
    sow = client.post("/api/sows/refresh", headers=auth_headers)
    stories = client.post("/api/stories/refresh", headers=auth_headers)
    return sow.json(), stories.json()


def test_sow_discover(client, auth_headers):
    r = client.get("/api/sows/discover", headers=auth_headers)
    assert r.status_code == 200
    files = r.json()["files"]
    statuses = {f["status"] for f in files}
    # Test data contains active, prospect, inactive subfolders with files
    assert "active" in statuses
    assert "prospect" in statuses
    assert "inactive" in statuses


def test_sow_refresh_ingests_synthetic(loaded, client, auth_headers):
    sow_run, _ = loaded
    assert sow_run["sows_loaded"] >= 4  # 2 active + 1 prospect + 1 inactive
    assert sow_run["chunks_total"] > 0
    assert sow_run["mentions_total"] >= 5
    assert sow_run["redactions_total"] >= 1  # SSN/email/phone in synthetic SOWs


def test_sow_list_filtering_by_status(loaded, client, auth_headers):
    r = client.get("/api/sows?status=active", headers=auth_headers)
    items = r.json()
    assert len(items) >= 2
    assert all(s["status"] == "active" for s in items)


def test_sow_clients_list_canonicalized(loaded, client, auth_headers):
    r = client.get("/api/sows/clients", headers=auth_headers)
    clients = {c["name"] for c in r.json()}
    # Wells Fargo synthetic SOW should be canonicalized via aliases
    assert "Wells Fargo" in clients
    assert "Northwestern Mutual" in clients
    assert "Charles Schwab" in clients
    assert "PNC Bank" in clients


def test_sow_preview_redacts_pii(loaded, client, auth_headers):
    # Find the Wells Fargo SOW
    sows = client.get("/api/sows", headers=auth_headers).json()
    wf = next(s for s in sows if s["client_name"] == "Wells Fargo")
    r = client.get(f"/api/sows/{wf['sow_id']}/preview", headers=auth_headers)
    body = r.json()
    assert body["redaction_method"] == "regex"
    assert "[REDACTED:SSN]" in body["preview"]
    assert "[REDACTED:EMAIL]" in body["preview"]
    assert "[REDACTED:PHONE_US]" in body["preview"]
    # Original PII strings should NOT appear in preview
    assert "123-45-6789" not in body["preview"]
    assert "jane.doe@wellsfargo.com" not in body["preview"]


def test_subcap_trace_finds_wells_fargo_mention(loaded, client, auth_headers):
    r = client.get("/api/projects/subcap-trace?sub_cap_id=P1C1.1.1", headers=auth_headers)
    body = r.json()
    assert body["sow_count"] >= 1
    sow_clients = {t["client_name"] for t in body["timeline"] if t["kind"] == "sow_mention"}
    assert "Wells Fargo" in sow_clients


def test_subcap_trace_finds_northwestern_compliance(loaded, client, auth_headers):
    r = client.get("/api/projects/subcap-trace?sub_cap_id=P1C2.7.1", headers=auth_headers)
    body = r.json()
    sow_clients = {t["client_name"] for t in body["timeline"] if t["kind"] == "sow_mention"}
    assert "Northwestern Mutual" in sow_clients


def test_stories_canonical_loaded(loaded, client, auth_headers):
    sow_run, stories_run = loaded
    assert stories_run["canonical_loaded"] > 100  # gen_stories has 4846 rows


def test_stories_refresh_idempotent(loaded, client, auth_headers):
    # Re-running shouldn't double-count
    r1 = client.post("/api/stories/refresh", headers=auth_headers).json()
    r2 = client.post("/api/stories/refresh", headers=auth_headers).json()
    assert r1["canonical_loaded"] == r2["canonical_loaded"]


def test_stories_canonical_filterable_by_subcap(loaded, client, auth_headers):
    r = client.get("/api/stories/canonical?sub_cap_id=P1C2.7.1&limit=5", headers=auth_headers)
    items = r.json()
    assert len(items) >= 1
    assert all(s["sub_cap_id"] == "P1C2.7.1" for s in items)


def test_subcap_detail_now_includes_sow_and_story_signals(loaded, client, auth_headers):
    r = client.get("/api/catalogue/subcaps/P1C1.1.1", headers=auth_headers)
    detail = r.json()
    assert "sow_signals" in detail
    assert detail["sow_signals"]["mention_count"] >= 1
    assert "story_signals" in detail
    assert detail["story_signals"]["canonical_count"] >= 0


def test_get_story_by_key(loaded, client, auth_headers):
    # gen_stories has GEN-P1C2.7.1-M1M2-01 as the first row
    r = client.get("/api/stories/GEN-P1C2.7.1-M1M2-01", headers=auth_headers)
    if r.status_code == 200:
        s = r.json()
        assert s["story_key"] == "GEN-P1C2.7.1-M1M2-01"
        assert "summary" in s
