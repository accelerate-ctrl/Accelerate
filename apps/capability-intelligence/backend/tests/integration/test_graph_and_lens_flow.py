"""End-to-end Batch 2 flow: ingest Pillar 1, build KG, query lenses."""
import pytest


@pytest.fixture
def ingested(client, auth_headers):
    """Ingest Pillar 1 once for the test."""
    r = client.post("/api/sheets/refresh/P1", headers=auth_headers)
    assert r.status_code == 200
    return r.json()


def test_kg_summary_after_ingest(ingested, client, auth_headers):
    r = client.get("/api/graph/summary", headers=auth_headers)
    assert r.status_code == 200
    s = r.json()
    # 199 subcaps + 4 categories + 1 pillar + 36 L1 + 45 L3 + many L4 + many UC + tags + themes + maturity + 8 clusters + 10 SVs + stages
    assert s["nodes_total"] > 200
    assert s["edges_total"] > 200
    by_kind = s["nodes_by_type"]
    assert by_kind.get("Subcap", 0) >= 100
    assert by_kind.get("Pillar", 0) >= 1
    assert by_kind.get("Cluster", 0) == 9  # 8 + VCC-00 (unclassified)
    assert by_kind.get("Subvertical", 0) == 10
    by_edge = s["edges_by_type"]
    assert by_edge.get("BELONGS_TO", 0) >= 100
    assert by_edge.get("MAPS_TO_STAGE", 0) > 100
    assert by_edge.get("APPLIES_TO", 0) > 100


def test_kg_elements_filtered_by_kinds(ingested, client, auth_headers):
    r = client.get("/api/graph/elements?kinds=Subcap,Category&max_nodes=50", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    kinds = {n["data"]["kind"] for n in body["nodes"]}
    assert kinds <= {"Subcap", "Category"}
    assert len(body["nodes"]) <= 50


def test_kg_neighborhood(ingested, client, auth_headers):
    r = client.get("/api/graph/neighborhood/Subcap:P1C1.1.1?hops=1", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    ids = {n["data"]["id"] for n in body["nodes"]}
    assert "Subcap:P1C1.1.1" in ids
    # P1C1 category is a 1-hop neighbor
    assert "Category:P1C1" in ids


def test_kg_centrality(ingested, client, auth_headers):
    r = client.get("/api/graph/centrality?metric=degree&limit=10", headers=auth_headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) <= 10
    assert all("score" in it and "kind" in it for it in items)


def test_kg_communities(ingested, client, auth_headers):
    r = client.get("/api/graph/communities", headers=auth_headers)
    assert r.status_code == 200
    comms = r.json()
    assert isinstance(comms, list)
    assert len(comms) >= 1


def test_kg_impact(ingested, client, auth_headers):
    # The pillar node is upstream of every category — removing it impacts all 4
    r = client.get("/api/graph/impact/Pillar:P1", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    affected_kinds = {a["kind"] for a in body["affected"]}
    assert "Category" in affected_kinds


def test_lens_subverticals_clusters_uc_families(ingested, client, auth_headers):
    r = client.get("/api/lens/subverticals", headers=auth_headers)
    assert len(r.json()) == 10
    r = client.get("/api/lens/clusters", headers=auth_headers)
    codes = [c["code"] for c in r.json()]
    assert "VCC-01" in codes and "VCC-08" in codes
    r = client.get("/api/lens/uc-tag-families", headers=auth_headers)
    assert len(r.json()) == 5


def test_value_chain_atlas(ingested, client, auth_headers):
    r = client.get("/api/lens/value-chain-atlas", headers=auth_headers)
    body = r.json()
    assert len(body["clusters"]) == 9  # 8 + VCC-00
    total_subcaps = sum(c["total_subcaps"] for c in body["clusters"])
    assert total_subcaps > 100  # many (subcap, stage) combinations


def test_value_chain_atlas_filtered_by_subvertical(ingested, client, auth_headers):
    r = client.get("/api/lens/value-chain-atlas?subvertical_code=RB", headers=auth_headers)
    body = r.json()
    assert body["subvertical_code"] == "RB"
    # Each stage in the response should be tagged with RB
    for c in body["clusters"]:
        for s in c["stages"]:
            assert s["subvertical_code"] == "RB"


def test_subvertical_compare(ingested, client, auth_headers):
    r = client.get("/api/lens/subvertical-compare/P1C1.1.1", headers=auth_headers)
    body = r.json()
    assert body["sub_cap_id"] == "P1C1.1.1"
    assert len(body["rows"]) == 10
    # Pillar 1 universal subcap should be applicable in every subvertical
    assert all(row["applicable"] for row in body["rows"])


def test_maturity_heatmap(ingested, client, auth_headers):
    r = client.get("/api/lens/maturity-heatmap?pillar_id=P1", headers=auth_headers)
    body = r.json()
    assert body["levels"] == ["M1", "M2", "M3", "M4", "M5"]
    assert len(body["rows"]) >= 100
    sample = body["rows"][0]
    assert len(sample["cells"]) == 5


def test_use_case_explorer(ingested, client, auth_headers):
    r = client.get("/api/lens/use-case-explorer", headers=auth_headers)
    body = r.json()
    assert body["total_use_cases"] > 100
    assert len(body["families"]) >= 1


def test_platform_catalog(ingested, client, auth_headers):
    r = client.get("/api/lens/platform-catalog", headers=auth_headers)
    body = r.json()
    assert body["total_platforms"] >= 30
    vendors = {v["vendor"] for v in body["vendors"]}
    assert "Salesforce" in vendors
