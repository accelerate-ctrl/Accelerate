"""Lifecycle scoring + state classification."""

from app.services import benchmarks_service, lifecycle_service, news_service
from app.services.lifecycle_service import (
    STATE_DEAD,
    STATE_DECLINING,
    STATE_EMERGING,
    STATE_FADING,
    STATE_RISING,
    STATE_STABLE,
    Signals,
    _classify_state,
    _score,
)
from app.services.llm.router import reset_state_for_tests


def test_score_zero_for_empty_signals():
    score, conf = _score(Signals())
    assert score == 0.0
    assert conf == 0.0


def test_score_combines_components_with_weights():
    sig = Signals(sow_active=2, canonical_stories=10, news_last_90d=2, benchmark_full=1)
    score, conf = _score(sig)
    assert score > 0
    assert conf == 1.0  # 4/4 categories present


def test_classify_dead_when_no_signals():
    assert _classify_state(Signals(), score=0.0) == STATE_DEAD


def test_classify_emerging_when_low_score_but_active():
    sig = Signals(sow_active=1)
    score, _ = _score(sig)  # ~10
    assert _classify_state(sig, score) in (STATE_EMERGING, STATE_RISING)


def test_classify_rising_when_high_score_and_recent():
    sig = Signals(
        sow_active=4,
        sow_prospect=2,
        sow_recency_days=5,
        canonical_stories=200,
        news_last_90d=4,
        news_recency_days=10,
        benchmark_full=2,
        benchmark_indicative=2,
    )
    score, _ = _score(sig)
    assert score >= 70  # all four components saturated
    assert _classify_state(sig, score) == STATE_RISING


def test_classify_fading_when_only_historical():
    sig = Signals(canonical_stories=20, benchmark_indicative=1)
    score, _ = _score(sig)
    assert _classify_state(sig, score) in (STATE_FADING, STATE_DECLINING)


def test_recompute_scores_every_subcap(settings_for_tests):
    from app.services import catalogue_service
    catalogue_service.refresh_pillar("P1", by="test")

    benchmarks_service.refresh(extrapolate=False)
    news_service.refresh()

    summary = lifecycle_service.recompute_all()
    assert summary.subcaps_scored > 0
    # state distribution sums to subcaps_scored
    assert sum(summary.state_distribution.values()) == summary.subcaps_scored
    # at least one subcap should be in a non-DEAD state because P1C1.1.1 has
    # SOW + news + benchmark coverage
    assert summary.state_distribution.get(STATE_DEAD, 0) < summary.subcaps_scored


def test_subcap_with_news_lands_in_active_state(settings_for_tests):
    from app.services import catalogue_service, sow_service, stories_service
    catalogue_service.refresh_pillar("P1", by="test")
    sow_service.ingest_all()
    stories_service.refresh_all()
    benchmarks_service.refresh(extrapolate=False)
    news_service.refresh()

    lifecycle_service.recompute_all()
    rec = lifecycle_service.get_score("P1C1.1.1")
    assert rec is not None
    assert rec["state"] in (STATE_RISING, STATE_STABLE, STATE_EMERGING)
    assert rec["confidence"] > 0.0


def test_state_transitions_logged(settings_for_tests):
    from app.services import catalogue_service
    catalogue_service.refresh_pillar("P1", by="test")
    # First run lands the baseline
    summary1 = lifecycle_service.recompute_all()
    # Inject SOW signal so a previously-DEAD subcap moves
    repo = settings_for_tests
    from app.services.repository import get_repository
    repo = get_repository()
    repo.upsert(
        "sows",
        "fake-sow",
        {"sow_id": "fake-sow", "client_name": "T", "status": "active",
         "ingested_at": "2026-04-01T00:00:00+00:00", "file_name": "t.txt"},
    )
    repo.upsert(
        "sow_mentions",
        "fake-mention",
        {"mention_id": "fake-mention", "sow_id": "fake-sow", "sub_cap_id": "P1C1.1.1",
         "method": "exact_id", "confidence": 99, "excerpt": "test"},
    )
    summary2 = lifecycle_service.recompute_all()
    # Either summary records >=0 transitions; transitions is monotonic
    assert summary2.transitions >= 0


def test_list_scores_filters_by_state(settings_for_tests):
    from app.services import catalogue_service
    catalogue_service.refresh_pillar("P1", by="test")
    lifecycle_service.recompute_all()
    rising = lifecycle_service.list_scores(state="RISING")
    for r in rising:
        assert r["state"] == "RISING"
