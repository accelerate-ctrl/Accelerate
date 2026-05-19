"""PII redaction — fail-closed in production (IMP-15).

Two redaction backends ship in the same surface:

* **Regex** — fast deterministic redaction for ``EMAIL`` / ``PHONE_US`` /
  ``SSN`` / Luhn-validated ``CREDIT_CARD``. Always available; used in
  dev + tests.
* **Cloud DLP** — google-cloud-dlp adapter (placeholder seam in this
  module). Production runs MUST route through here when ``ENV=prod``.

Fail-closed rule (per Plan §Phase 5):
    When ``Settings.env == "prod"`` and the Cloud DLP adapter is not
    available, :func:`redact_required` raises :class:`DlpUnavailable`
    instead of silently falling back to regex. Callers in SOW ingest
    use :func:`redact_required` so a misconfigured prod environment
    fails ingestion rather than persisting un-DLP-cleared text.

Every redact call also emits a structured ``dlp.redacted`` log line with
the per-kind counts so the audit trail records which PII categories were
seen in each SOW (IMP-15 logging requirement).
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ─── Exceptions ─────────────────────────────────────────────────────────────


class DlpUnavailable(RuntimeError):
    """Raised in prod when Cloud DLP cannot be reached and fail-closed."""


# ─── Regex backend ──────────────────────────────────────────────────────────


_PATTERNS = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PHONE_US", re.compile(r"\b(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
]


@dataclass
class RedactionResult:
    text: str
    redaction_summary: dict[str, int]
    redaction_method: str  # "regex" | "dlp"


def redact(text: str) -> RedactionResult:
    """Regex redaction. Always returns ``method='regex'``."""
    summary: dict[str, int] = {}
    out = text
    for kind, pat in _PATTERNS:
        def repl(m: re.Match, _kind: str = kind) -> str:
            summary[_kind] = summary.get(_kind, 0) + 1
            return f"[REDACTED:{_kind}]"
        if kind == "CREDIT_CARD":
            def maybe_repl(m: re.Match) -> str:
                digits = re.sub(r"\D", "", m.group(0))
                if not (13 <= len(digits) <= 19) or not _luhn(digits):
                    return m.group(0)
                summary[kind] = summary.get(kind, 0) + 1
                return f"[REDACTED:{kind}]"
            out = pat.sub(maybe_repl, out)
        else:
            out = pat.sub(repl, out)
    return RedactionResult(text=out, redaction_summary=summary, redaction_method="regex")


def _luhn(digits: str) -> bool:
    s = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        n = int(ch)
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        s += n
    return s % 10 == 0


# ─── Cloud DLP adapter (pluggable) ──────────────────────────────────────────

# Production wires this to google.cloud.dlp_v2 in
# ``app.services.dlp_adapters.gcp_dlp``. Until that lands, the seam stays
# None and ``redact_required`` falls back to regex in non-prod envs,
# raises ``DlpUnavailable`` in prod.
_dlp_backend: Callable[[str], RedactionResult] | None = None


def register_dlp_backend(fn: Callable[[str], RedactionResult] | None) -> None:
    """Test + production hook: wire a Cloud-DLP-backed implementation."""
    global _dlp_backend
    _dlp_backend = fn


def is_dlp_available() -> bool:
    return _dlp_backend is not None


# ─── Public fail-closed surface ─────────────────────────────────────────────


def _current_env() -> str:
    """Resolve the env in a way tests can monkeypatch cheaply.

    Settings is the source of truth in production, but ``ENV`` /
    ``CAPABILITY_INTELLIGENCE_ENV`` env vars are honoured first so DLP
    can be exercised without booting the full Settings stack.
    """
    env = os.getenv("ENV") or os.getenv("CAPABILITY_INTELLIGENCE_ENV")
    if env:
        return env
    try:
        from app.config import get_settings
        return get_settings().env
    except Exception:  # noqa: BLE001
        return "dev"


def _dlp_strict() -> bool:
    """Whether DLP must succeed (fail-closed). Defaults to True in prod."""
    explicit = os.getenv("DLP_REQUIRED")
    if explicit is not None:
        return explicit.lower() in {"1", "true", "yes", "on"}
    return _current_env() == "prod"


def redact_required(text: str, *, context: str | None = None) -> RedactionResult:
    """Redact with fail-closed semantics suitable for SOW ingest.

    Behaviour matrix:

    +---------+------------------+----------------------------------+
    | env     | DLP backend wired| outcome                          |
    +=========+==================+==================================+
    | prod    | yes              | run DLP backend                  |
    +---------+------------------+----------------------------------+
    | prod    | no               | raise :class:`DlpUnavailable`    |
    +---------+------------------+----------------------------------+
    | dev/    | yes              | run DLP backend                  |
    | staging | no               | regex fallback + warn            |
    +---------+------------------+----------------------------------+
    """
    if _dlp_backend is not None:
        try:
            result = _dlp_backend(text)
            _log_redaction(result, context=context, fallback=False)
            return result
        except Exception as exc:  # noqa: BLE001
            if _dlp_strict():
                raise DlpUnavailable(
                    f"Cloud DLP backend raised in fail-closed env: {exc}"
                ) from exc
            logger.warning(
                "dlp.backend_failed",
                extra={"context": context, "error": str(exc)},
            )
            result = redact(text)
            _log_redaction(result, context=context, fallback=True)
            return result

    if _dlp_strict():
        raise DlpUnavailable(
            "ENV=prod and DLP backend not registered — refusing to fall back "
            "to regex redaction. Wire google-cloud-dlp via "
            "dlp_service.register_dlp_backend()."
        )

    result = redact(text)
    _log_redaction(result, context=context, fallback=False)
    return result


def _log_redaction(
    result: RedactionResult, *, context: str | None, fallback: bool
) -> None:
    """IMP-15 — log PII categories per redacted document.

    The log is structured so Cloud Logging can index ``redaction_method``
    + ``categories`` + ``context`` and surface counts per SOW.
    """
    payload: dict[str, Any] = {
        "redaction_method": result.redaction_method,
        "categories": dict(result.redaction_summary),
        "total_redactions": sum(result.redaction_summary.values()),
        "context": context,
    }
    if fallback:
        payload["fallback_to_regex"] = True
    logger.info("dlp.redacted", extra=payload)
