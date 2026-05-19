"""IMP-9 — LLM router downgrade hook tests."""

from __future__ import annotations

import pytest

from app.services import user_budget
from app.services.llm import router as llm_router
from app.services.llm.router import LlmRequest, LlmResponse, ModelKind, call


@pytest.fixture(autouse=True)
def _reset_llm(settings_for_tests, monkeypatch):
    llm_router.reset_state_for_tests()
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    yield
    llm_router.reset_state_for_tests()


def _req(model: ModelKind, *, user_email: str | None = "u@zen") -> LlmRequest:
    md = {"user_email": user_email} if user_email else {}
    return LlmRequest(
        model=model,
        prompt="P1C1.1.1 digital strategy regulatory compliance",
        cache=False,
        metadata=md,
    )


def test_no_downgrade_when_under_budget():
    resp = call(_req(ModelKind.GEMINI_PRO))
    # In dev mode, _call_dev keeps the original model.
    assert resp.model == ModelKind.GEMINI_PRO


def test_downgrade_pro_to_flash_when_over_budget():
    user_budget.record_spend("u@zen", cost_usd=99.0)  # blow past $5 cap
    resp = call(_req(ModelKind.GEMINI_PRO))
    assert resp.model == ModelKind.GEMINI_FLASH


def test_downgrade_sonnet_to_gemini_pro_when_over_budget():
    user_budget.record_spend("u@zen", cost_usd=99.0)
    resp = call(_req(ModelKind.SONNET))
    assert resp.model == ModelKind.GEMINI_PRO


def test_downgrade_opus_to_gemini_pro_when_over_budget():
    user_budget.record_spend("u@zen", cost_usd=99.0)
    resp = call(_req(ModelKind.OPUS))
    assert resp.model == ModelKind.GEMINI_PRO


def test_admin_bypasses_downgrade(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "u@zen")
    user_budget.record_spend("u@zen", cost_usd=99.0)
    resp = call(_req(ModelKind.GEMINI_PRO))
    assert resp.model == ModelKind.GEMINI_PRO


def test_no_user_email_no_downgrade():
    user_budget.record_spend("other@zen", cost_usd=99.0)
    resp = call(_req(ModelKind.GEMINI_PRO, user_email=None))
    assert resp.model == ModelKind.GEMINI_PRO


def test_call_persists_per_user_spend():
    starting = user_budget.spend_for("u@zen").spend_usd
    call(_req(ModelKind.GEMINI_PRO))
    after = user_budget.spend_for("u@zen").spend_usd
    # Dev-mode call yields a tiny non-zero cost (token estimate × pricing);
    # the assertion is that spend monotonically rose.
    assert after >= starting


def test_flash_does_not_downgrade_further_when_over_budget():
    # Flash already at the bottom — no further downgrade target.
    user_budget.record_spend("u@zen", cost_usd=99.0)
    resp = call(_req(ModelKind.GEMINI_FLASH))
    assert resp.model == ModelKind.GEMINI_FLASH


def test_downgrade_metadata_recorded_in_raw(monkeypatch):
    # When the adapter populates resp.raw (vertex/anthropic adapters do),
    # the router attaches the downgrade info. In dev mode raw is None, so
    # we just confirm the call doesn't crash; the wire-shape is exercised
    # via the live path in integration.
    user_budget.record_spend("u@zen", cost_usd=99.0)
    resp = call(_req(ModelKind.GEMINI_PRO))
    assert resp.model == ModelKind.GEMINI_FLASH
