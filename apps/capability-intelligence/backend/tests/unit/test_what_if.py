"""What-If simulator — pure-function deltas."""

import pytest

from app.services import (
    benchmarks_service,
    lifecycle_service,
    news_service,
    vendor_intel_service,
    what_if_service,
)
from app.services.what_if_service import _classify, _recompute_score


@pytest.fixture
def seeded(settings_for_tests):
    from app.services import catalogue_service, sow_service, stories_service
    catalogue_service.refresh_pillar("P1", by="test")
    sow_service.ingest_all()
    stories_service.refresh_all()
    benchmarks_service.refresh(extrapolate=False)
    news_service.refresh()
    lifecycle_service.recompute_all()
    vendor_intel_service.refresh()
    return settings_for_tests


def test_recompute_score_zero_for_empty_signals():
    assert _recompute_score({}) == 0.0


def test_classify_dead_when_zero():
    assert _classify({}, 0.0) == "DEAD"


def test_simulate_with_no_actions(seeded):
    result = what_if_service.simulate([])
    assert result.actions_applied == 0
    assert result.state_changes == []


def test_simulate_add_sow_promotes_score(seeded):
    # P1C1.1.1 is RISING with score ~51; adding 3 active SOWs should saturate.
    actions = [
        {"kind": "add_sow_mention", "target": {"sub_cap_id": "P1C1.1.1"}},
        {"kind": "add_sow_mention", "target": {"sub_cap_id": "P1C1.1.1"}},
        {"kind": "add_sow_mention", "target": {"sub_cap_id": "P1C1.1.1"}},
    ]
    result = what_if_service.simulate(actions)
    assert result.actions_applied == 3
    assert result.state_changes
    last = result.state_changes[-1]
    assert last["after"]["score"] >= last["before"]["score"]


def test_simulate_set_lifecycle_state(seeded):
    actions = [
        {"kind": "set_lifecycle_state",
         "target": {"sub_cap_id": "P1C1.1.1", "state": "STABLE"}},
    ]
    result = what_if_service.simulate(actions)
    assert result.actions_applied == 1
    assert result.state_changes[0]["after"]["state"] == "STABLE"


def test_simulate_invalid_state_ignored(seeded):
    actions = [
        {"kind": "set_lifecycle_state",
         "target": {"sub_cap_id": "P1C1.1.1", "state": "INVALID"}},
    ]
    result = what_if_service.simulate(actions)
    assert result.actions_applied == 0


def test_simulate_unknown_subcap_ignored(seeded):
    actions = [
        {"kind": "add_sow_mention", "target": {"sub_cap_id": "P9C9.9.9"}},
    ]
    result = what_if_service.simulate(actions)
    assert result.actions_applied == 0


def test_simulate_promote_vendor(seeded):
    actions = [
        {"kind": "promote_vendor",
         "target": {"vendor_id": "salesforce_financial_services_cloud",
                    "cohort_id": "us_banks_gsib", "adoption_pct": 95.0}},
    ]
    result = what_if_service.simulate(actions)
    assert result.actions_applied == 1
    assert result.adoption_changes[0]["after_pct"] == 95.0


def test_simulate_does_not_mutate_repository(seeded):
    """Critical: simulator is read-only."""
    from app.services.repository import get_repository

    repo = get_repository()
    before = repo.get("lifecycle_scores", "P1C1.1.1")
    what_if_service.simulate([
        {"kind": "set_lifecycle_state",
         "target": {"sub_cap_id": "P1C1.1.1", "state": "DEAD"}},
    ])
    after = repo.get("lifecycle_scores", "P1C1.1.1")
    assert before["state"] == after["state"]


def test_simulate_unknown_kind_skipped(seeded):
    actions = [{"kind": "invent_universe", "target": {}}]
    result = what_if_service.simulate(actions)
    assert result.actions_applied == 0
