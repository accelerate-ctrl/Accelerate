"""IMP-15 — DLP fail-closed semantics for SOW ingest.

Phase 5 hardens the redaction surface: in production, SOW ingest must
refuse to persist text when Cloud DLP is not available, instead of
silently falling back to regex.
"""

from __future__ import annotations

import logging

import pytest

from app.services import dlp_service
from app.services.dlp_service import (
    DlpUnavailable,
    RedactionResult,
    is_dlp_available,
    redact,
    redact_required,
    register_dlp_backend,
)


@pytest.fixture(autouse=True)
def _reset_dlp_backend():
    register_dlp_backend(None)
    yield
    register_dlp_backend(None)


def test_redact_required_uses_regex_in_dev(monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.delenv("DLP_REQUIRED", raising=False)
    result = redact_required("Contact jane@x.com")
    assert "[REDACTED:EMAIL]" in result.text
    assert result.redaction_method == "regex"


def test_redact_required_raises_in_prod_when_backend_missing(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    with pytest.raises(DlpUnavailable):
        redact_required("Contact jane@x.com")


def test_redact_required_runs_backend_when_registered(monkeypatch):
    calls = []

    def fake_backend(text: str) -> RedactionResult:
        calls.append(text)
        return RedactionResult(
            text="[scrubbed]",
            redaction_summary={"EMAIL": 1},
            redaction_method="dlp",
        )

    register_dlp_backend(fake_backend)
    monkeypatch.setenv("ENV", "prod")
    result = redact_required("Contact jane@x.com")
    assert result.text == "[scrubbed]"
    assert result.redaction_method == "dlp"
    assert calls == ["Contact jane@x.com"]


def test_redact_required_falls_back_in_dev_when_backend_raises(monkeypatch):
    def boom(text: str) -> RedactionResult:
        raise RuntimeError("api down")

    register_dlp_backend(boom)
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.delenv("DLP_REQUIRED", raising=False)
    result = redact_required("Contact jane@x.com")
    assert result.redaction_method == "regex"
    assert "[REDACTED:EMAIL]" in result.text


def test_redact_required_raises_in_prod_when_backend_fails(monkeypatch):
    def boom(text: str) -> RedactionResult:
        raise RuntimeError("api down")

    register_dlp_backend(boom)
    monkeypatch.setenv("ENV", "prod")
    with pytest.raises(DlpUnavailable):
        redact_required("Contact jane@x.com")


def test_dlp_required_env_var_overrides_env(monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("DLP_REQUIRED", "true")
    with pytest.raises(DlpUnavailable):
        redact_required("Contact jane@x.com")


def test_dlp_required_false_in_prod_allows_regex(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("DLP_REQUIRED", "false")
    result = redact_required("Contact jane@x.com")
    assert result.redaction_method == "regex"


def test_is_dlp_available_reflects_registration():
    assert is_dlp_available() is False
    register_dlp_backend(lambda t: RedactionResult(text=t, redaction_summary={}, redaction_method="dlp"))
    assert is_dlp_available() is True
    register_dlp_backend(None)
    assert is_dlp_available() is False


def test_log_records_pii_categories(monkeypatch, caplog):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.delenv("DLP_REQUIRED", raising=False)
    with caplog.at_level(logging.INFO, logger="app.services.dlp_service"):
        redact_required("Contact jane@x.com SSN 123-45-6789", context="sow-1")
    matching = [r for r in caplog.records if r.message == "dlp.redacted"]
    assert matching, f"expected dlp.redacted log, got {[r.message for r in caplog.records]}"
    rec = matching[-1]
    assert getattr(rec, "context", None) == "sow-1"
    assert getattr(rec, "categories", {}).get("EMAIL") == 1


def test_log_marks_fallback_when_backend_fails(monkeypatch, caplog):
    def boom(text: str) -> RedactionResult:
        raise RuntimeError("boom")

    register_dlp_backend(boom)
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.delenv("DLP_REQUIRED", raising=False)
    with caplog.at_level(logging.INFO, logger="app.services.dlp_service"):
        redact_required("jane@x.com")
    matching = [r for r in caplog.records if r.message == "dlp.redacted"]
    assert matching
    rec = matching[-1]
    assert getattr(rec, "fallback_to_regex", False) is True


def test_existing_redact_unchanged():
    # Regression — the original sync redact API still works exactly as before.
    result = redact("call 415-555-0123 SSN 111-22-3333")
    assert "[REDACTED:PHONE_US]" in result.text
    assert "[REDACTED:SSN]" in result.text
    assert result.redaction_method == "regex"
