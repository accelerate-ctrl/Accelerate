"""F06 cluster-aware benchmark CI tests (Phase 4.2).

The hierarchical_bootstrap_ci helper resamples primary_source_id
clusters (not individual observations) so the CI width respects the
fact that 50 metrics from one regulator filing are not 50 independent
observations. These tests verify both the bootstrap CI and the new
cluster-aware mean/stdev fields are produced correctly.
"""

import statistics

from app.services.benchmarks_service import (
    _compute_distribution,
    hierarchical_bootstrap_ci,
)


def _obs(primary_id: str, value: float, *, id_: str | None = None) -> dict:
    return {
        "id": id_ or f"obs-{primary_id}-{value}",
        "primary_source_id": primary_id,
        "value": value,
        "source_kind": "filing",
        "ingested_at": "2026-01-01T00:00:00Z",
    }


# ─── Cluster-aware mean + stdev ────────────────────────────────────────────


def test_cluster_aware_mean_uses_one_value_per_primary():
    """Three obs from one primary + one obs from another → cluster_aware
    mean should be the average of the two cluster reps, NOT the naive
    mean over all four observations.
    """
    obs = [
        _obs("filing-A", 10),
        _obs("filing-A", 12),
        _obs("filing-A", 14),  # cluster A median = 12
        _obs("filing-B", 100),  # cluster B median = 100
    ]
    out = hierarchical_bootstrap_ci(obs, B=200)
    # Naive mean of values would be (10+12+14+100)/4 = 34.
    # Cluster-aware mean is (12 + 100) / 2 = 56.
    assert abs(out["cluster_aware_mean"] - 56.0) < 0.001
    # Cluster-aware stdev should be the pstdev of [12, 100] = 44.
    assert abs(out["cluster_aware_stdev"] - statistics.pstdev([12, 100])) < 0.01


def test_cluster_aware_zero_when_one_cluster():
    """One cluster → no spread; cluster-aware stdev should be 0."""
    obs = [_obs("A", v) for v in (1, 2, 3, 4, 5)]
    out = hierarchical_bootstrap_ci(obs, B=200)
    assert out["cluster_aware_stdev"] == 0.0
    assert out["effective_n"] == 1


def test_effective_n_counts_unique_primaries():
    obs = [
        _obs("A", 1), _obs("A", 2), _obs("A", 3),
        _obs("B", 10),
        _obs("C", 100),
    ]
    out = hierarchical_bootstrap_ci(obs, B=200)
    # 5 raw obs but only 3 distinct primaries.
    assert out["effective_n"] == 3


def test_ci_width_respects_cluster_count():
    """CIs computed from many distinct primaries should be tighter
    than CIs computed from the same observation count concentrated in
    one primary."""
    # Tight case: 30 obs from 30 distinct primaries (true sample size).
    tight = [_obs(f"p-{i}", 50 + i % 5) for i in range(30)]
    tight_out = hierarchical_bootstrap_ci(tight, B=500)
    # Wide case: 30 obs from 2 primaries (heavily clustered).
    wide = [_obs("p1", 50) for _ in range(15)] + [_obs("p2", 60) for _ in range(15)]
    wide_out = hierarchical_bootstrap_ci(wide, B=500)
    tight_width = tight_out["ci_high"] - tight_out["ci_low"]
    wide_width = wide_out["ci_high"] - wide_out["ci_low"]
    # Wide-case (only 2 clusters) must produce a wider CI band than
    # the 30-cluster case, no matter how many observations.
    assert wide_width >= tight_width


def test_empty_observations_returns_zero_envelope():
    out = hierarchical_bootstrap_ci([], B=10)
    assert out["effective_n"] == 0
    assert out["cluster_aware_mean"] == 0.0
    assert out["cluster_aware_stdev"] == 0.0


def test_bootstrap_is_deterministic_for_same_seed():
    obs = [_obs(f"p-{i}", 50 + i) for i in range(20)]
    a = hierarchical_bootstrap_ci(obs, B=200, seed=99)
    b = hierarchical_bootstrap_ci(obs, B=200, seed=99)
    assert a["median"] == b["median"]
    assert a["ci_low"] == b["ci_low"]
    assert a["ci_high"] == b["ci_high"]


def test_compute_distribution_surfaces_cluster_aware_fields():
    """The persisted distribution row must carry the new F06 fields so
    Benchmarks Studio + chat can read them without recomputing."""
    obs = [_obs(f"p{i}", 50 + i) for i in range(8)]
    out = _compute_distribution("metric-x", "cohort-x", "2026Q1", obs)
    assert "cluster_aware_mean" in out
    assert "cluster_aware_stdev" in out
    assert out["effective_n"] == 8
    assert out["ci_method"] == "hierarchical-bootstrap"


def test_naive_stdev_still_present_for_back_compat():
    """The legacy stdev field must still be emitted so existing
    consumers (PPTX export, chat snippets) keep working."""
    obs = [_obs(f"p{i}", 50 + i) for i in range(8)]
    out = _compute_distribution("metric-x", "cohort-x", "2026Q1", obs)
    assert "stdev" in out
    assert out["stdev"] >= 0.0
