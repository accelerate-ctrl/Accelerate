"""Phase 5 eval harness — regression-gate behaviour."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.services import eval_service
from app.services.eval import eval_harness
from app.services.repository import get_repository


def _stub_eval_summary(*runs: dict) -> dict:
    return {
        "started_at": "2026-05-19T00:00:00Z",
        "completed_at": "2026-05-19T00:00:01Z",
        "runs": list(runs),
        "summary": {"total_cases": 0, "total_passed": 0, "by_kind": {}},
    }


def _run(
    dataset_id: str,
    *,
    kind: str = "digest_priorities",
    mean_score: float = 0.9,
    pass_rate: float = 0.8,
    n_cases: int = 4,
    n_passed: int = 3,
) -> dict:
    return {
        "run_id": f"eval-{dataset_id}-1",
        "dataset_id": dataset_id,
        "kind": kind,
        "started_at": "2026-05-19T00:00:00Z",
        "completed_at": "2026-05-19T00:00:01Z",
        "n_cases": n_cases,
        "n_passed": n_passed,
        "pass_rate": pass_rate,
        "mean_score": mean_score,
        "cases": [],
    }


def test_first_run_with_no_baseline_does_not_regress(settings_for_tests):
    summary = _stub_eval_summary(_run("ds-a", mean_score=0.7))
    with patch.object(eval_service, "run_eval", return_value=summary):
        result = eval_harness.run_harness()
    assert result.passed
    assert result.n_datasets == 1
    assert result.verdicts[0].regressed is False
    assert "no baseline" in (result.verdicts[0].reason or "")


def test_regression_detected_when_score_drops_past_tolerance(settings_for_tests):
    eval_harness.set_baseline(
        "ds-a", mean_score=0.9, pass_rate=0.9, tolerance=0.05
    )
    summary = _stub_eval_summary(_run("ds-a", mean_score=0.80))
    with patch.object(eval_service, "run_eval", return_value=summary):
        result = eval_harness.run_harness()
    assert not result.passed
    assert result.n_regressed == 1
    assert result.verdicts[0].regressed is True
    assert "mean_score" in (result.verdicts[0].reason or "")


def test_pass_within_tolerance_band(settings_for_tests):
    eval_harness.set_baseline(
        "ds-a", mean_score=0.90, pass_rate=0.9, tolerance=0.05
    )
    # 0.86 ≥ 0.85 floor — within band, no regression.
    summary = _stub_eval_summary(_run("ds-a", mean_score=0.86))
    with patch.object(eval_service, "run_eval", return_value=summary):
        result = eval_harness.run_harness()
    assert result.passed
    assert result.n_regressed == 0


def test_pass_rate_floor_blocks_when_min_pass_rate_set(settings_for_tests):
    eval_harness.set_baseline(
        "ds-a",
        mean_score=0.5,
        pass_rate=0.9,
        tolerance=0.5,
        min_pass_rate=0.8,
    )
    summary = _stub_eval_summary(_run("ds-a", mean_score=0.5, pass_rate=0.4))
    with patch.object(eval_service, "run_eval", return_value=summary):
        result = eval_harness.run_harness()
    assert not result.passed
    assert "pass_rate" in (result.verdicts[0].reason or "")


def test_set_baseline_from_run_persists_to_repo(settings_for_tests):
    run = _run("ds-b", mean_score=0.42, pass_rate=0.3)
    baseline = eval_harness.set_baseline_from_run(run, tolerance=0.07)
    assert baseline.mean_score == 0.42
    assert baseline.tolerance == 0.07
    stored = get_repository().get(eval_harness.BASELINE_COLLECTION, "ds-b")
    assert stored is not None
    assert stored["mean_score"] == 0.42


def test_list_baselines_returns_all_persisted(settings_for_tests):
    eval_harness.set_baseline("ds-a", mean_score=0.9, pass_rate=0.9)
    eval_harness.set_baseline("ds-b", mean_score=0.8, pass_rate=0.7)
    rows = eval_harness.list_baselines()
    ids = {r["dataset_id"] for r in rows}
    assert {"ds-a", "ds-b"} <= ids


def test_subset_via_dataset_ids_filters(settings_for_tests):
    summary = _stub_eval_summary(
        _run("ds-a", mean_score=0.5), _run("ds-b", mean_score=0.5)
    )
    with patch.object(eval_service, "run_eval", return_value=summary):
        result = eval_harness.run_harness(dataset_ids=["ds-b"])
    assert result.n_datasets == 1
    assert result.verdicts[0].dataset_id == "ds-b"


def test_overall_mean_is_average_of_verdicts(settings_for_tests):
    summary = _stub_eval_summary(
        _run("ds-a", mean_score=0.6), _run("ds-b", mean_score=0.8)
    )
    with patch.object(eval_service, "run_eval", return_value=summary):
        result = eval_harness.run_harness()
    assert result.overall_mean == pytest.approx(0.7)


def test_dict_round_trips_json(settings_for_tests):
    summary = _stub_eval_summary(_run("ds-a", mean_score=0.7))
    with patch.object(eval_service, "run_eval", return_value=summary):
        result = eval_harness.run_harness()
    payload = json.loads(json.dumps(result.to_dict()))
    assert payload["n_datasets"] == 1
    assert payload["verdicts"][0]["dataset_id"] == "ds-a"


def test_cli_run_strict_returns_nonzero_on_regression(
    settings_for_tests, capsys
):
    eval_harness.set_baseline(
        "ds-a", mean_score=0.9, pass_rate=0.9, tolerance=0.01
    )
    summary = _stub_eval_summary(_run("ds-a", mean_score=0.5))
    with patch.object(eval_service, "run_eval", return_value=summary):
        rc = eval_harness.main(["run", "--strict"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "REGRESS" in captured.out


def test_cli_run_strict_returns_zero_when_no_regression(
    settings_for_tests, capsys
):
    eval_harness.set_baseline(
        "ds-a", mean_score=0.5, pass_rate=0.5, tolerance=0.1
    )
    summary = _stub_eval_summary(_run("ds-a", mean_score=0.55))
    with patch.object(eval_service, "run_eval", return_value=summary):
        rc = eval_harness.main(["run", "--strict"])
    assert rc == 0


def test_cli_set_baseline_writes_to_repo(settings_for_tests, capsys):
    summary = _stub_eval_summary(_run("ds-x", mean_score=0.4, pass_rate=0.4))
    with patch.object(eval_service, "run_eval", return_value=summary):
        rc = eval_harness.main(["set-baseline", "--tolerance", "0.02"])
    assert rc == 0
    stored = get_repository().get(eval_harness.BASELINE_COLLECTION, "ds-x")
    assert stored is not None
    assert stored["tolerance"] == 0.02


def test_cli_list_baselines_json_includes_captured(
    settings_for_tests, capsys
):
    eval_harness.set_baseline("ds-z", mean_score=0.7, pass_rate=0.6)
    rc = eval_harness.main(["list-baselines", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(b["dataset_id"] == "ds-z" for b in payload)


def test_cli_run_json_emits_machine_payload(settings_for_tests, capsys):
    summary = _stub_eval_summary(_run("ds-a", mean_score=0.7))
    with patch.object(eval_service, "run_eval", return_value=summary):
        rc = eval_harness.main(["run", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["n_datasets"] == 1


def test_baseline_tolerance_defaults_apply_when_not_provided(
    settings_for_tests,
):
    b = eval_harness.set_baseline("ds-d", mean_score=0.9, pass_rate=0.9)
    assert b.tolerance == eval_harness.DEFAULT_TOLERANCE
    assert b.min_pass_rate == eval_harness.DEFAULT_MIN_PASS_RATE
