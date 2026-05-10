"""Suggestions lifecycle (pending → applied / rejected)."""

import pytest

from app.services import consultant_loop, suggestions_service
from app.services.llm.router import ModelKind, reset_state_for_tests


def _seed(settings_for_tests):
    reset_state_for_tests()
    return consultant_loop.run(
        query="audit subcap",
        sub_cap_id="P1C1.1.1",
        synth_model=ModelKind.GEMINI_FLASH,
    )


def test_seed_creates_pending_suggestions(settings_for_tests):
    _seed(settings_for_tests)
    pending = suggestions_service.list_suggestions(status="pending")
    assert pending, "consultant loop should produce at least one pending suggestion"
    assert all(s["status"] == "pending" for s in pending)


def test_apply_transitions_to_applied(settings_for_tests):
    _seed(settings_for_tests)
    pending = suggestions_service.list_suggestions(status="pending")
    sid = pending[0]["id"]
    out = suggestions_service.apply_suggestion(sid, actor="alice@zennify.com")
    assert out["status"] == "applied"
    assert out["decided_by"] == "alice@zennify.com"


def test_apply_twice_raises(settings_for_tests):
    _seed(settings_for_tests)
    sid = suggestions_service.list_suggestions(status="pending")[0]["id"]
    suggestions_service.apply_suggestion(sid, actor="x")
    with pytest.raises(ValueError):
        suggestions_service.apply_suggestion(sid, actor="x")


def test_reject_with_reason(settings_for_tests):
    _seed(settings_for_tests)
    sid = suggestions_service.list_suggestions(status="pending")[0]["id"]
    out = suggestions_service.reject_suggestion(sid, actor="bob@zennify.com", reason="duplicate")
    assert out["status"] == "rejected"
    assert out["reject_reason"] == "duplicate"


def test_stats_reflects_lifecycle(settings_for_tests):
    _seed(settings_for_tests)
    items = suggestions_service.list_suggestions()
    assert items
    sid = items[0]["id"]
    suggestions_service.apply_suggestion(sid, actor="x")
    s = suggestions_service.stats()
    assert s["applied"] >= 1
    assert s["total"] == s["pending"] + s["applied"] + s["rejected"]
