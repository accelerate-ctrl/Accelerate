"""Eval harness — golden-dataset scoring."""

import pytest

from app.services import (
    benchmarks_service,
    digest_service,
    eval_service,
    lifecycle_service,
    news_service,
)
from app.services.llm.router import reset_state_for_tests


@pytest.fixture
def seeded(settings_for_tests):
    from app.services import catalogue_service, sow_service
    catalogue_service.refresh_pillar("P1", by="test")
    sow_service.ingest_all()
    benchmarks_service.refresh(extrapolate=False)
    news_service.refresh()
    lifecycle_service.recompute_all()
    reset_state_for_tests()
    return settings_for_tests


def test_list_datasets_returns_seed_when_empty(settings_for_tests):
    datasets = eval_service.list_datasets()
    kinds = {d["kind"] for d in datasets}
    assert {"digest_priorities", "gate_consistency", "citation_grounding"} <= kinds


def test_run_eval_all_kinds(seeded):
    # produce a digest first so digest_priorities scoring has something to compare
    digest_service.generate(subvertical="retail-banking", period="2026-Q2", priority_limit=3)
    out = eval_service.run_eval()
    assert out["runs"]
    kinds = {r["kind"] for r in out["runs"]}
    assert "digest_priorities" in kinds
    # totals are non-negative
    assert out["summary"]["total_cases"] >= 0


def test_run_eval_specific_dataset(seeded):
    digest_service.generate(subvertical="retail-banking", period="2026-Q2", priority_limit=3)
    out = eval_service.run_eval(dataset_id="digest_priorities_bootstrap")
    assert len(out["runs"]) == 1
    assert out["runs"][0]["kind"] == "digest_priorities"


def test_run_eval_unknown_dataset_raises(seeded):
    with pytest.raises(KeyError):
        eval_service.run_eval(dataset_id="not-a-dataset")


def test_eval_run_persists(seeded):
    digest_service.generate(subvertical="retail-banking", period="2026-Q2", priority_limit=3)
    out = eval_service.run_eval(dataset_id="digest_priorities_bootstrap")
    runs = eval_service.list_runs()
    assert any(r["run_id"] == out["runs"][0]["run_id"] for r in runs)


def test_digest_priorities_scoring_overlap(seeded):
    """Bootstrap labels expect P1C1.1.{1,2,3} for retail-banking 2026-Q2.
    Live lifecycle output puts those at top → high overlap."""
    digest_service.generate(subvertical="retail-banking", period="2026-Q2", priority_limit=5)
    out = eval_service.run_eval(dataset_id="digest_priorities_bootstrap")
    run = out["runs"][0]
    assert run["mean_score"] > 0
