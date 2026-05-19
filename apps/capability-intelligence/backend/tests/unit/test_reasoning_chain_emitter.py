"""Tests for the lightweight reasoning-chain emitter (QA_AUDIT F02)."""

import pytest

from app.services.reasoning_chain_emitter import (
    CHAIN_COLLECTION,
    ChainEmitter,
    emit_chain,
    list_chains,
)
from app.services.repository import get_repository


def test_empty_chain_commits_with_pass_overall(settings_for_tests):
    with emit_chain(operation="test_op") as chain:
        pass
    rows = list_chains(operation="test_op")
    assert len(rows) == 1
    assert rows[0]["overall"] == "pass"
    assert rows[0]["operation"] == "test_op"
    assert rows[0]["chain_id"].startswith("chain-test_op-")
    assert rows[0]["_schema_version"] == "reasoning-chain-v1"


def test_steps_are_recorded_in_order(settings_for_tests):
    with emit_chain(operation="news_impact") as chain:
        chain.step("retrieve", input_summary="60-subcap inventory")
        chain.step("llm", model="gemini-flash", tokens_in=200, tokens_out=80, cost_usd=0.0009)
        chain.step("validate", output_summary="ok")
    rows = list_chains(operation="news_impact")
    assert len(rows[0]["steps"]) == 3
    assert [s["name"] for s in rows[0]["steps"]] == ["retrieve", "llm", "validate"]
    assert rows[0]["steps"][1]["model"] == "gemini-flash"
    assert rows[0]["total_cost_usd"] == 0.0009


def test_attach_sources_and_output(settings_for_tests):
    with emit_chain(operation="suggest") as chain:
        chain.attach_sources([
            {"id": "src-1", "url": "https://x.com/a", "tier": "T1"},
            {"id": "src-2", "url": "https://y.com/b", "tier": "T2"},
        ])
        chain.attach_output({
            "claims": [{"text": "a", "label": "FACT"}],
            "summary": "X happened",
        })
    rows = list_chains(operation="suggest")
    assert len(rows[0]["sources"]) == 2
    assert rows[0]["sources"][0]["tier"] == "T1"
    assert rows[0]["output"]["summary"] == "X happened"


def test_block_exception_captures_failure_and_reraises(settings_for_tests):
    """The chain must persist with overall=fail even when the wrapped
    block raises, so audit dashboards can see the failure path.
    """
    with pytest.raises(ValueError):
        with emit_chain(operation="failing_op") as chain:
            chain.step("retrieve", input_summary="x")
            raise ValueError("synthetic failure")
    rows = list_chains(operation="failing_op")
    assert len(rows) == 1
    assert rows[0]["overall"] == "fail"
    assert rows[0]["failure"]["error_type"] == "ValueError"
    assert "synthetic failure" in rows[0]["failure"]["error_message"]
    # One step recorded before the failure.
    assert len(rows[0]["steps"]) == 1


def test_commit_is_idempotent(settings_for_tests):
    """Calling commit() twice must not duplicate the chain."""
    emitter = ChainEmitter(operation="idempotent")
    emitter.step("x")
    emitter.commit()
    emitter.commit()
    rows = list_chains(operation="idempotent")
    assert len(rows) == 1


def test_persistence_failure_does_not_propagate(settings_for_tests, monkeypatch):
    """If the repo upsert fails for any reason, the chain emit path
    must NOT propagate — the AI work already happened.
    """
    def boom(*_args, **_kwargs):
        raise RuntimeError("firestore down")

    monkeypatch.setattr(
        "app.services.reasoning_chain_emitter.get_repository",
        lambda: type("Repo", (), {"upsert": staticmethod(boom)})(),
    )
    # Should not raise.
    with emit_chain(operation="db_fail") as chain:
        chain.step("x")


def test_list_chains_filters_by_subcap(settings_for_tests):
    with emit_chain(operation="x", sub_cap_id="P1C1.1.1") as c:
        c.step("a")
    with emit_chain(operation="x", sub_cap_id="P1C2.1.1") as c:
        c.step("b")
    with emit_chain(operation="x") as c:
        c.step("c")
    rows = list_chains(operation="x", sub_cap_id="P1C1.1.1")
    assert len(rows) == 1
    assert rows[0]["sub_cap_id"] == "P1C1.1.1"


def test_list_chains_sorted_newest_first(settings_for_tests):
    with emit_chain(operation="sortable") as c:
        c.step("a")
    with emit_chain(operation="sortable") as c:
        c.step("b")
    rows = list_chains(operation="sortable")
    assert len(rows) == 2
    # Newest-first
    assert rows[0]["started_at"] >= rows[1]["started_at"]


def test_chain_carries_pillar_and_subvertical_metadata(settings_for_tests):
    with emit_chain(
        operation="contextual",
        sub_cap_id="P1C1.1.1",
        pillar_id="P1",
        subvertical="RB",
        leverage_tier="MEDIUM",
    ) as chain:
        chain.step("x")
    rows = list_chains(operation="contextual")
    assert rows[0]["pillar_id"] == "P1"
    assert rows[0]["subvertical"] == "RB"
    assert rows[0]["leverage_tier"] == "MEDIUM"


def test_step_summary_truncated_to_400_chars(settings_for_tests):
    huge = "X" * 1000
    with emit_chain(operation="huge") as chain:
        chain.step("x", input_summary=huge, output_summary=huge)
    rows = list_chains(operation="huge")
    step = rows[0]["steps"][0]
    assert len(step["input_summary"]) == 400
    assert len(step["output_summary"]) == 400


def test_total_cost_aggregates_across_steps(settings_for_tests):
    with emit_chain(operation="cost") as chain:
        chain.step("a", cost_usd=0.001)
        chain.step("b", cost_usd=0.002)
        chain.step("c", cost_usd=0.0005)
    rows = list_chains(operation="cost")
    assert rows[0]["total_cost_usd"] == 0.0035


def test_repository_chain_is_indexed_by_chain_id(settings_for_tests):
    """The chain doc id must equal the emitter's chain_id so the
    Reasoning Chain Viewer can deep-link to /reasoning/{chain_id}.
    """
    with emit_chain(operation="indexed") as chain:
        chain.step("x")
    target_id = chain.chain_id
    doc = get_repository().get(CHAIN_COLLECTION, target_id)
    assert doc is not None
    assert doc["chain_id"] == target_id
