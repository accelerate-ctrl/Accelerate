"""End-to-end consultant loop in dev-mode."""

from app.services import consultant_loop, news_service
from app.services.llm.router import ModelKind, reset_state_for_tests


def test_run_loop_writes_chain_and_suggestions(settings_for_tests):
    reset_state_for_tests()
    # Seed news so external retrieval has something
    news_service.refresh()

    result = consultant_loop.run(
        query="audit the digital strategy document subcap evidence",
        sub_cap_id="P1C1.1.1",
        synth_model=ModelKind.GEMINI_FLASH,
    )

    assert result.chain_id.startswith("chain-")
    # 8 logged steps: clarify, retrieve_internal, retrieve_external, synthesize,
    # adversarial, propose_suggestions, gate, finalize
    assert len(result.steps) == 8
    assert {s.name for s in result.steps} == {
        "clarify", "retrieve_internal", "retrieve_external", "synthesize",
        "adversarial", "propose_suggestions", "gate", "finalize",
    }

    # Spec G1..G8 + 7 auxiliary gates = 15
    assert len(result.gates["results"]) == 15
    names = {r["name"] for r in result.gates["results"]}
    assert {"g1_novelty", "g2_source_quality", "g3_ers", "g4_independence",
            "g5_consistency", "g6_adversarial", "g7_drift", "g8_absence"} <= names

    # Chain persisted
    persisted = consultant_loop.get_chain(result.chain_id)
    assert persisted is not None
    assert persisted["sub_cap_id"] == "P1C1.1.1"

    # Suggestions persisted with status=pending
    listed = consultant_loop.list_chains(sub_cap_id="P1C1.1.1")
    assert any(c["chain_id"] == result.chain_id for c in listed)


def test_loop_overall_classification(settings_for_tests):
    reset_state_for_tests()
    news_service.refresh()
    result = consultant_loop.run(
        query="audit subcap",
        sub_cap_id="P1C1.1.1",
        synth_model=ModelKind.GEMINI_PRO,
    )
    assert result.overall in ("pass", "warn", "fail")
