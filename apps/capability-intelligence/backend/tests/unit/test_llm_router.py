"""LLM router + cache + cost tracker — dev-mode determinism."""

from app.services.llm.router import LlmRequest, ModelKind, call, reset_state_for_tests
from app.services.llm.cache import LlmCache
from app.services.llm.cost_tracker import BudgetExceeded, CostTracker


def test_dev_mode_is_deterministic(settings_for_tests):
    reset_state_for_tests()
    req = LlmRequest(model=ModelKind.GEMINI_FLASH, prompt="extract claims about banking", max_tokens=400)
    a = call(req)
    reset_state_for_tests()
    b = call(req)
    assert a.text == b.text
    assert a.model == ModelKind.GEMINI_FLASH


def test_cache_returns_cached_on_second_call(settings_for_tests):
    reset_state_for_tests()
    req = LlmRequest(model=ModelKind.SONNET, prompt="cache me", system="be brief")
    first = call(req)
    second = call(req)
    assert first.cached is False
    assert second.cached is True
    assert first.text == second.text


def test_cache_key_distinguishes_temperature(settings_for_tests):
    reset_state_for_tests()
    cache = LlmCache()
    r1 = LlmRequest(model=ModelKind.SONNET, prompt="hello", temperature=0.0)
    r2 = LlmRequest(model=ModelKind.SONNET, prompt="hello", temperature=0.5)
    call(r1)
    assert cache.get(r1) is not None
    assert cache.get(r2) is None


def test_dev_mode_dispatch_picks_correct_response_for_extract(settings_for_tests):
    reset_state_for_tests()
    resp = call(LlmRequest(
        model=ModelKind.GEMINI_PRO,
        prompt="please extract claims from the evidence below",
        system="extract claims",
    ))
    assert "claims" in resp.text  # canned JSON
    assert resp.cost_usd == 0.0  # dev-mode is free


def test_dev_mode_dispatch_for_adversarial(settings_for_tests):
    reset_state_for_tests()
    resp = call(LlmRequest(
        model=ModelKind.SONNET,
        prompt="critique these claims",
        system="adversarial reviewer",
    ))
    assert "verdict" in resp.text


def test_cost_tracker_records_spend(settings_for_tests):
    reset_state_for_tests()
    tracker = CostTracker()
    assert tracker.spend_today() == 0.0
    tracker.record(ModelKind.SONNET, 100, 100, 0.0012)
    tracker.record(ModelKind.OPUS, 100, 100, 0.006)
    assert round(tracker.spend_today(), 4) == 0.0072
    summary = tracker.summary()
    assert summary.today_calls == 2
    assert "sonnet" in summary.by_model
    assert summary.by_model["sonnet"] > 0


def test_cost_tracker_blocks_over_budget(settings_for_tests, monkeypatch):
    reset_state_for_tests()
    monkeypatch.setenv("DAILY_SPEND_CEILING_USD", "1.0")
    monkeypatch.setenv("COST_THROTTLE_PCT", "0.5")
    from app.config import get_settings
    get_settings.cache_clear()

    tracker = CostTracker()
    tracker.record(ModelKind.OPUS, 1000, 1000, 0.60)
    try:
        tracker.assert_within_budget()
        raise AssertionError("expected BudgetExceeded")
    except BudgetExceeded:
        pass
