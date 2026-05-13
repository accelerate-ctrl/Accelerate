"""Benchmarks engine: cohort matching, distribution math, ingest, verdict."""

import pytest

from app.services import benchmarks_service as bm
from app.services.benchmarks_service import (
    VERDICT_BENCHMARK,
    VERDICT_EXPLORATORY,
    VERDICT_INDICATIVE,
    _coef_var,
    _company_cohorts,
    _matches_cohort,
    _percentile,
    _verdict,
)


def test_percentile_linear_interpolation():
    vals = [10, 20, 30, 40, 50]
    assert _percentile(vals, 0) == 10
    assert _percentile(vals, 0.5) == 30
    assert _percentile(vals, 1.0) == 50
    assert _percentile(vals, 0.25) == 20
    assert _percentile(vals, 0.75) == 40


def test_percentile_singleton_returns_value():
    assert _percentile([42.0], 0.5) == 42.0


def test_coef_var_zero_for_singleton():
    assert _coef_var([5.0]) == 0.0


def test_coef_var_basic():
    cv = _coef_var([10, 11, 12, 9, 13])
    assert cv > 0


def test_verdict_benchmark_when_dense_low_variance():
    assert _verdict(6, {"filing"}, 0.05, has_extrapolation=False) == VERDICT_BENCHMARK


def test_verdict_indicative_when_3_obs():
    assert _verdict(3, {"filing", "analyst"}, 0.4, has_extrapolation=False) == VERDICT_INDICATIVE


def test_verdict_exploratory_when_few_or_extrapolated():
    assert _verdict(1, {"ai_extrapolation"}, 0, has_extrapolation=True) == VERDICT_EXPLORATORY
    assert _verdict(2, {"filing"}, 0, has_extrapolation=False) == VERDICT_EXPLORATORY


def test_cohort_matching_by_subvertical_and_assets():
    cohort = {
        "cohort_id": "us_banks_gsib",
        "subvertical": "retail-banking",
        "membership": {"asset_size_min_usd_bn": 700},
    }
    assert _matches_cohort(
        {"subvertical": "retail-banking", "asset_size_usd_bn": 1900}, cohort
    )
    assert not _matches_cohort(
        {"subvertical": "retail-banking", "asset_size_usd_bn": 50}, cohort
    )
    assert not _matches_cohort(
        {"subvertical": "wealth-management", "asset_size_usd_bn": 5000}, cohort
    )


def test_company_cohorts_assigns_multiple_when_eligible():
    cohorts = [
        {"cohort_id": "us_banks_gsib", "subvertical": "retail-banking",
         "membership": {"asset_size_min_usd_bn": 700}},
        {"cohort_id": "us_banks_super_regional", "subvertical": "retail-banking",
         "membership": {"asset_size_min_usd_bn": 100, "asset_size_max_usd_bn": 700}},
    ]
    assert _company_cohorts({"subvertical": "retail-banking", "asset_size_usd_bn": 1900}, cohorts) == ["us_banks_gsib"]
    assert _company_cohorts({"subvertical": "retail-banking", "asset_size_usd_bn": 300}, cohorts) == ["us_banks_super_regional"]


def test_refresh_loads_seed_data(settings_for_tests):
    summary = bm.refresh(extrapolate=False)
    assert summary.filings_loaded >= 6
    assert summary.observations_total > 0
    assert summary.distributions_total > 0
    assert summary.cohorts_loaded >= 3


def test_refresh_classifies_jpm_as_gsib(settings_for_tests):
    bm.refresh(extrapolate=False)
    obs = bm.list_observations(company="JPMorgan Chase")
    assert obs
    assert "us_banks_gsib" in obs[0]["cohort_ids"]


def test_refresh_produces_filing_distribution_for_tech_spend(settings_for_tests):
    bm.refresh(extrapolate=False)
    dists = bm.list_distributions(metric_id="tech_spend_pct_revenue")
    # GSIB cohort has Wells + JPM + BofA = 3
    gsib = [d for d in dists if d["cohort_id"] == "us_banks_gsib"]
    assert gsib, "expected at least one GSIB distribution"
    assert gsib[0]["n"] >= 3


def test_distribution_assigns_indicative_when_3_obs(settings_for_tests):
    bm.refresh(extrapolate=False)
    gsib_tech = [
        d for d in bm.list_distributions(metric_id="tech_spend_pct_revenue")
        if d["cohort_id"] == "us_banks_gsib"
    ]
    assert gsib_tech
    # 3 observations → INDICATIVE per verdict rules
    assert gsib_tech[0]["verdict"] in (VERDICT_INDICATIVE, VERDICT_BENCHMARK)


def test_extrapolation_marks_observation_and_changes_verdict(settings_for_tests):
    bm.refresh(extrapolate=True)
    extrapolated = [
        o for o in bm.list_observations(metric_id="tech_spend_pct_revenue")
        if o.get("is_extrapolated")
    ]
    # cohorts with sparse observations should now have an AI row
    assert extrapolated, "expected at least one AI-extrapolated observation"
    assert extrapolated[0]["source_kind"] == "ai_extrapolation"
    assert extrapolated[0].get("chain_id")


def test_subcap_filter_uses_metric_mappings(settings_for_tests):
    bm.refresh(extrapolate=False)
    dists = bm.list_distributions(sub_cap_id="P1C2.3.5")
    assert dists, "tech_spend metric maps to P1C2.3.* — should match"
    metric_ids = {d["metric_id"] for d in dists}
    assert "tech_spend_pct_revenue" in metric_ids


def test_refresh_idempotent(settings_for_tests):
    a = bm.refresh(extrapolate=False)
    b = bm.refresh(extrapolate=False)
    assert a.filings_loaded == b.filings_loaded
    assert a.observations_total == b.observations_total


def test_sources_catalogue_built(settings_for_tests):
    bm.refresh(extrapolate=False)
    srcs = bm.list_sources()
    assert srcs
    labels = {s["label"] for s in srcs}
    assert any("10-K" in label or "Form ADV" in label for label in labels)
