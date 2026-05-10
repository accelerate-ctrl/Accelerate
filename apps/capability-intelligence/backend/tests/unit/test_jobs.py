"""Cloud Run Job runner — every registered job runs cleanly."""

import pytest

from app.jobs.runner import ALL_JOBS, _coerce, _parse_kwargs, execute, main


@pytest.fixture
def seeded(settings_for_tests):
    from app.services import (
        benchmarks_service,
        catalogue_service,
        lifecycle_service,
        news_service,
        sow_service,
        stories_service,
    )
    catalogue_service.refresh_pillar("P1", by="test")
    sow_service.ingest_all()
    stories_service.refresh_all()
    benchmarks_service.refresh(extrapolate=False)
    news_service.refresh()
    lifecycle_service.recompute_all()
    return settings_for_tests


def test_all_14_jobs_registered():
    assert len(ALL_JOBS) == 14
    assert "news_poll" in ALL_JOBS
    assert "digest_quarterly" in ALL_JOBS


def test_unknown_job_raises():
    with pytest.raises(SystemExit):
        execute("not-a-real-job")


def test_news_poll_runs_clean(seeded):
    out = execute("news_poll")
    assert out["status"] == "ok"
    assert "result" in out
    assert "news_loaded" in out["result"]


def test_public_filings_poll_runs_clean(seeded):
    out = execute("public_filings_poll")
    assert out["status"] == "ok"
    assert "filings_loaded" in out["result"]


def test_jira_incremental_runs_clean(seeded):
    out = execute("jira_incremental")
    assert out["status"] == "ok"
    # in dev mode jira creds aren't set; service no-ops with empty result
    assert "jira_loaded" in out["result"]


def test_sow_incremental_runs_clean(seeded):
    out = execute("sow_incremental")
    assert out["status"] == "ok"


def test_sow_full_reindex_runs_clean(seeded):
    out = execute("sow_full_reindex")
    assert out["status"] == "ok"


def test_lifecycle_scoring_daily_runs_clean(seeded):
    out = execute("lifecycle_scoring_daily")
    assert out["status"] == "ok"
    assert out["result"]["subcaps_scored"] > 0


def test_benchmark_extrapolation_run_clean(seeded):
    out = execute("benchmark_extrapolation_run")
    assert out["status"] == "ok"
    # extrapolation may fire some cohorts depending on seed data
    assert "extrapolations_total" in out["result"]


def test_benchmark_recompute_quarterly_clean(seeded):
    out = execute("benchmark_recompute_quarterly")
    assert out["status"] == "ok"


def test_digest_quarterly_with_period_arg(seeded):
    out = execute("digest_quarterly", period="2026-Q2", priority_limit=2,
                  subverticals="retail-banking")
    assert out["status"] == "ok"
    assert out["result"]["period"] == "2026-Q2"
    assert out["result"]["digests"]
    assert out["result"]["digests"][0]["subvertical"] == "retail-banking"


def test_deep_audit_weekly_runs_clean(seeded):
    out = execute("deep_audit_weekly")
    assert out["status"] == "ok"
    # Returns the audit report shape
    assert "report_id" in out["result"]


def test_eval_run_weekly_runs_clean(seeded):
    out = execute("eval_run_weekly")
    assert out["status"] == "ok"
    assert "runs" in out["result"]


def test_citation_verify_daily_runs_clean(seeded):
    out = execute("citation_verify_daily")
    assert out["status"] == "ok"
    assert "probed" in out["result"]


def test_drift_check_daily_runs_clean(seeded):
    out = execute("drift_check_daily")
    assert out["status"] == "ok"
    assert "drift_count" in out["result"]


def test_evidence_promotion_nightly_promotes(seeded):
    out = execute("evidence_promotion_nightly")
    assert out["status"] == "ok"
    # Should have promoted at least the canonical-stories rows
    assert out["result"]["promoted"] > 0


def test_runner_main_returns_zero(seeded):
    rc = main(["news_poll"])
    assert rc == 0


def test_runner_main_propagates_arg(seeded):
    rc = main([
        "digest_quarterly",
        "--arg", "period=2026-Q2",
        "--arg", "priority_limit=2",
        "--arg", "subverticals=retail-banking",
    ])
    assert rc == 0


def test_kwargs_coercion():
    assert _coerce("42") == 42
    assert _coerce("3.14") == 3.14
    assert _coerce("true") is True
    assert _coerce("false") is False
    assert _coerce("hello") == "hello"


def test_parse_kwargs_handles_repeats():
    out = _parse_kwargs(["a=1", "b=2.5", "c=hello"])
    assert out == {"a": 1, "b": 2.5, "c": "hello"}
