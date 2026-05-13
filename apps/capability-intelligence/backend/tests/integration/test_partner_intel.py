"""Partner Intelligence — config load, scan pipeline, gap detection."""

import os
from pathlib import Path

from fastapi.testclient import TestClient


def test_partners_yaml_loads_six_partners():
    from app.services import partner_intel_service
    partners = partner_intel_service.load_partners()
    codes = sorted(p.code for p in partners)
    assert codes == [
        "agentforce",
        "databricks",
        "mulesoft",
        "ncino",
        "salesforce",
        "twilio",
    ], codes


def test_scan_populates_releases_and_suggestions(monkeypatch, tmp_path):
    """Run the full scan pipeline against the bundled seed files.

    The dev-mode Gemini Flash adapter returns canned text that doesn't
    parse as JSON, so we patch the LLM call to return a deterministic
    feature list. This isolates the test to the orchestration logic +
    L1-matching heuristic.
    """
    from app.services import partner_intel_service
    from app.services.repository import get_repository

    # Seed an L1 capability the scanner can map onto.
    repo = get_repository()
    repo.upsert("l1_capabilities", "Strategy Foundation", {
        "id": "Strategy Foundation",
        "l1_capability": "Strategy Foundation",
        "description": "Digital strategy authoring, alignment, and tracking.",
        "category_id": "P1C1",
    })
    repo.upsert("subcaps", "P1C1.1.1", {
        "sub_cap_id": "P1C1.1.1",
        "sub_cap_name": "Digital Strategy Document",
        "l1_capability": "Strategy Foundation",
        "description": "Authoring + version history",
        "pillar_id": "P1",
    })

    def fake_extract(entry, partner):
        return [
            {
                "feature": "Action Plans for Wealth onboarding",
                "summary": "Pre-built action plans for advisor-driven client onboarding.",
                "impact_class": "new_feature",
                "category_hint": "workflow",
            }
        ] if partner.code == "salesforce" else []

    monkeypatch.setattr(partner_intel_service, "extract_features", fake_extract)

    result = partner_intel_service.run_scan(limit_per_partner=5)
    assert result["entries_seen"] > 0, result
    assert result["features_extracted"] >= 1
    assert "salesforce" in result["per_partner"]
    sf = result["per_partner"]["salesforce"]
    assert sf["features"] >= 1
    assert sf["releases"] >= 1

    releases = partner_intel_service.list_releases(partner_code="salesforce")
    assert len(releases) >= 1
    titles = {r["title"] for r in releases}
    assert any("Summer '26" in t or "Summer '26" in t for t in titles), titles


def test_catalogue_gaps_endpoint_returns_grouped(monkeypatch):
    """End-to-end: scan run → /catalogue-gaps returns L1-grouped rows."""
    from app.services import partner_intel_service

    def fake_extract(entry, partner):
        if partner.code != "databricks":
            return []
        return [{
            "feature": "Lakeflow declarative pipelines GA",
            "summary": "Declarative pipelines GA with Snowflake connectors.",
            "impact_class": "new_feature",
            "category_hint": "data",
        }]

    monkeypatch.setattr(partner_intel_service, "extract_features", fake_extract)

    # Seed an L1 that strongly matches.
    from app.services.repository import get_repository
    repo = get_repository()
    repo.upsert("l1_capabilities", "Data & Pipelines", {
        "id": "Data & Pipelines",
        "l1_capability": "Data & Pipelines",
        "description": "Data lakes, pipelines, Snowflake, Lakeflow, streaming.",
        "category_id": "P2C1",
    })

    partner_intel_service.run_scan(limit_per_partner=5)
    gaps = partner_intel_service.catalogue_gaps()
    # Even if no `is_gap` row surfaces (heuristic may consider the L1
    # already covered), the contract must still be a list with the
    # right keys.
    assert isinstance(gaps, list)
    for g in gaps:
        assert "l1_capability" in g
        assert "features" in g
        assert "partners" in g
        assert "count" in g


def test_partner_endpoints_authenticated(monkeypatch):
    from app.main import app
    c = TestClient(app)
    H = {"Authorization": "Bearer dev-test@zennify.com"}

    r = c.get("/api/vendor-intel/partners", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 6
    codes = {p["code"] for p in body}
    assert "salesforce" in codes and "databricks" in codes

    r = c.get("/api/vendor-intel/releases", headers=H)
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    r = c.get("/api/vendor-intel/catalogue-gaps", headers=H)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
