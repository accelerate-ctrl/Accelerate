"""Tests for the per-subcap news impact magnitude scoring (PRD FR-17).

The classifier returns a structured ``affected_subcaps`` list where each
entry carries a magnitude (HIGH / MEDIUM / LOW) and a short rationale.
Legacy callers still see ``affects_subcaps`` (flat id list) for back-
compat during the migration window.
"""

from unittest.mock import patch

from app.services import news_service


VALID_SUBCAPS = [
    {"sub_cap_id": "P1C1.1.1", "sub_cap_name": "Digital Strategy"},
    {"sub_cap_id": "P1C2.1.1", "sub_cap_name": "Governance Charter"},
    {"sub_cap_id": "P1C3.5.2", "sub_cap_name": "Open Banking API"},
]

BASE_ITEM = {
    "id": "news-001",
    "title": "OCC issues new open-banking rule for retail banks",
    "source": "occ.gov",
    "url": "https://occ.gov/news/2026-05-rule",
    "published_at": "2026-05-18T08:00:00Z",
    "text": "The OCC today published a new rule requiring retail banks to ...",
}




def test_synthesise_returns_structured_magnitudes(settings_for_tests):
    """The new schema emits affected_subcaps with magnitude + rationale."""
    payload = {
        "summary": "OCC rule on open banking impacts retail banks",
        "impact_class": "catalogue_extension",
        "affected_subcaps": [
            {
                "sub_cap_id": "P1C3.5.2",
                "magnitude": "HIGH",
                "rationale": "Direct regulator rule on this capability",
            },
            {
                "sub_cap_id": "P1C2.1.1",
                "magnitude": "MEDIUM",
                "rationale": "Governance implications",
            },
        ],
        "suggests_new_subcap": {"name": "Foo", "rationale": "r", "candidate_l1": "L1"},
        "confidence": 0.85,
    }
    with _stub_llm(payload):
        out = news_service.synthesise_impact(BASE_ITEM, subcaps=VALID_SUBCAPS)
    assert out["impact_class"] == "catalogue_extension"
    assert len(out["affected_subcaps"]) == 2
    high = out["affected_subcaps"][0]
    assert high["sub_cap_id"] == "P1C3.5.2"
    assert high["magnitude"] == "HIGH"
    assert "Direct regulator" in high["rationale"]
    # Back-compat: flat id list is the same set in magnitude order.
    assert out["affects_subcaps"] == ["P1C3.5.2", "P1C2.1.1"]


def test_no_impact_clears_affected_subcaps(settings_for_tests):
    """A no_impact verdict must zero the affected list even if the LLM
    leaks magnitudes through."""
    payload = {
        "summary": "Generic FS news",
        "impact_class": "no_impact",
        "affected_subcaps": [
            {"sub_cap_id": "P1C1.1.1", "magnitude": "LOW", "rationale": "weak"},
        ],
        "confidence": 0.2,
    }
    with _stub_llm(payload):
        out = news_service.synthesise_impact(BASE_ITEM, subcaps=VALID_SUBCAPS)
    assert out["impact_class"] == "no_impact"
    assert out["affected_subcaps"] == []
    assert out["affects_subcaps"] == []


def test_subcap_id_not_in_inventory_is_dropped(settings_for_tests):
    """Hallucinated subcap ids must be filtered before persistence."""
    payload = {
        "summary": "x",
        "impact_class": "reinforcement",
        "affected_subcaps": [
            {"sub_cap_id": "P1C1.1.1", "magnitude": "HIGH", "rationale": "ok"},
            {"sub_cap_id": "P9C99.9.9", "magnitude": "HIGH", "rationale": "fake"},
        ],
        "confidence": 0.7,
    }
    with _stub_llm(payload):
        out = news_service.synthesise_impact(BASE_ITEM, subcaps=VALID_SUBCAPS)
    assert [e["sub_cap_id"] for e in out["affected_subcaps"]] == ["P1C1.1.1"]


def test_unknown_magnitude_falls_back_to_low(settings_for_tests):
    payload = {
        "summary": "x",
        "impact_class": "reinforcement",
        "affected_subcaps": [
            {"sub_cap_id": "P1C1.1.1", "magnitude": "CRITICAL", "rationale": "x"},
        ],
        "confidence": 0.5,
    }
    with _stub_llm(payload):
        out = news_service.synthesise_impact(BASE_ITEM, subcaps=VALID_SUBCAPS)
    assert out["affected_subcaps"][0]["magnitude"] == "LOW"


def test_legacy_flat_list_shape_is_accepted(settings_for_tests):
    """The old ``affects_subcaps`` (flat string list) shape must still
    produce a valid response so cached LLM calls from the prior schema
    don't break."""
    payload = {
        "summary": "x",
        "impact_class": "reinforcement",
        "affects_subcaps": ["P1C1.1.1", "P1C2.1.1"],
        "confidence": 0.6,
    }
    with _stub_llm(payload):
        out = news_service.synthesise_impact(BASE_ITEM, subcaps=VALID_SUBCAPS)
    assert len(out["affected_subcaps"]) == 2
    # Legacy shape lacks rationales — they should be empty strings.
    assert all(e["rationale"] == "" for e in out["affected_subcaps"])
    # Default magnitude when not specified is LOW.
    assert all(e["magnitude"] == "LOW" for e in out["affected_subcaps"])


def test_results_sorted_by_magnitude(settings_for_tests):
    payload = {
        "summary": "x",
        "impact_class": "reinforcement",
        "affected_subcaps": [
            {"sub_cap_id": "P1C1.1.1", "magnitude": "LOW", "rationale": "a"},
            {"sub_cap_id": "P1C2.1.1", "magnitude": "HIGH", "rationale": "b"},
            {"sub_cap_id": "P1C3.5.2", "magnitude": "MEDIUM", "rationale": "c"},
        ],
        "confidence": 0.7,
    }
    with _stub_llm(payload):
        out = news_service.synthesise_impact(BASE_ITEM, subcaps=VALID_SUBCAPS)
    mags = [e["magnitude"] for e in out["affected_subcaps"]]
    assert mags == ["HIGH", "MEDIUM", "LOW"]


def test_affected_capped_at_four(settings_for_tests):
    payload = {
        "summary": "x",
        "impact_class": "reinforcement",
        "affected_subcaps": [
            {"sub_cap_id": "P1C1.1.1", "magnitude": "HIGH", "rationale": "a"},
            {"sub_cap_id": "P1C2.1.1", "magnitude": "HIGH", "rationale": "b"},
            {"sub_cap_id": "P1C3.5.2", "magnitude": "MEDIUM", "rationale": "c"},
        ],
        "confidence": 0.7,
    }
    # Even though the LLM emitted 3, the cap is a no-op; verify the
    # cap actually applies when the LLM emits 8.
    eight = [
        {"sub_cap_id": f"P1C{i+1}.1.1", "magnitude": "HIGH", "rationale": f"r{i}"}
        for i in range(8)
    ]
    inventory = [{"sub_cap_id": f"P1C{i+1}.1.1"} for i in range(8)]
    payload["affected_subcaps"] = eight
    with _stub_llm(payload):
        out = news_service.synthesise_impact(BASE_ITEM, subcaps=inventory)
    assert len(out["affected_subcaps"]) == 4


def test_llm_failure_returns_safe_defaults(settings_for_tests):
    """If the LLM call raises, the function returns a safe envelope so
    the batch job doesn't crash on one bad item."""
    def raising(_req):
        raise RuntimeError("boom")

    with patch("app.services.llm.router.call", new=raising):
        out = news_service.synthesise_impact(BASE_ITEM, subcaps=VALID_SUBCAPS)
    assert out["impact_class"] == "no_impact"
    assert out["affected_subcaps"] == []
    assert out["affects_subcaps"] == []
    assert out["confidence"] == 0.0


# ─── Phase 2.4 / F02 — reasoning-chain emission ────────────────────────────


def test_synthesise_emits_reasoning_chain(settings_for_tests):
    """Every call to synthesise_impact must persist a reasoning chain
    so the trust surface has a uniform audit row (QA_AUDIT F02)."""
    from app.services.reasoning_chain_emitter import list_chains

    payload = {
        "summary": "x",
        "impact_class": "reinforcement",
        "affected_subcaps": [
            {"sub_cap_id": "P1C1.1.1", "magnitude": "HIGH", "rationale": "x"},
        ],
        "confidence": 0.7,
    }
    with _stub_llm(payload):
        out = news_service.synthesise_impact(BASE_ITEM, subcaps=VALID_SUBCAPS)
    chains = list_chains(operation="news_impact")
    assert len(chains) == 1
    chain = chains[0]
    # The returned impact carries the chain id for FE deep-linking.
    assert out["chain_id"] == chain["chain_id"]
    # Three canonical steps were recorded.
    step_names = [s["name"] for s in chain["steps"]]
    assert step_names == ["retrieve", "llm", "validate"]
    # The source list captures the news item itself.
    assert any(s.get("id") == "news-001" for s in chain["sources"])


def test_chain_records_dropped_subcap_ids(settings_for_tests):
    """When the LLM hallucinates a subcap id, the validate step must
    record what was dropped so reviewers can see why an item is
    'almost' flagged but didn't make the cut.
    """
    from app.services.reasoning_chain_emitter import list_chains

    payload = {
        "summary": "x",
        "impact_class": "reinforcement",
        "affected_subcaps": [
            {"sub_cap_id": "P1C1.1.1", "magnitude": "HIGH", "rationale": "ok"},
            {"sub_cap_id": "P9C99.9.9", "magnitude": "HIGH", "rationale": "fake"},
        ],
        "confidence": 0.7,
    }
    with _stub_llm(payload):
        news_service.synthesise_impact(BASE_ITEM, subcaps=VALID_SUBCAPS)
    chain = list_chains(operation="news_impact")[0]
    validate_step = next(s for s in chain["steps"] if s["name"] == "validate")
    assert "P9C99.9.9" in validate_step["detail"]["dropped_subcap_ids"]


def test_chain_records_overall_pass_on_success(settings_for_tests):
    from app.services.reasoning_chain_emitter import list_chains

    payload = {
        "summary": "ok",
        "impact_class": "reinforcement",
        "affected_subcaps": [],
        "confidence": 0.3,
    }
    with _stub_llm(payload):
        news_service.synthesise_impact(BASE_ITEM, subcaps=VALID_SUBCAPS)
    chain = list_chains(operation="news_impact")[0]
    assert chain["overall"] == "pass"
    assert chain["failure"] is None


def test_chain_records_failure_when_llm_raises(settings_for_tests):
    from app.services.reasoning_chain_emitter import list_chains

    def raising(_req):
        raise RuntimeError("boom")

    with patch("app.services.llm.router.call", new=raising):
        news_service.synthesise_impact(BASE_ITEM, subcaps=VALID_SUBCAPS)
    chain = list_chains(operation="news_impact")[0]
    # The chain is persisted with overall=fail so the audit dashboard
    # can surface it; the function itself still returned a safe envelope.
    assert chain["overall"] == "fail"
    assert chain["failure"]["error_type"] == "RuntimeError"


# ─── helpers ───────────────────────────────────────────────────────────────


def _stub_llm(payload: dict):
    """Patch the LLM router ``call`` so news_service.synthesise_impact's
    in-function import receives our stub.
    """
    import json
    from types import SimpleNamespace

    def fake(_req):
        return SimpleNamespace(text=json.dumps(payload))

    return patch("app.services.llm.router.call", new=fake)
