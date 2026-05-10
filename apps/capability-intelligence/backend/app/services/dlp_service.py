"""PII redaction.

Local mode: regex-based redaction for SSN, US phone numbers, emails, credit-
card numbers (Luhn-validated). GCP mode (Cloud DLP) plugs into the same
`redact()` API — when `Settings.use_gcp` is true and a DLP template is
configured, we'll route there. Same return shape for both.

Note: this is intentionally conservative for local dev. Production must use
Cloud DLP for FS-grade compliance.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Patterns are deliberately strict to keep false-positives low.
_PATTERNS = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PHONE_US", re.compile(r"\b(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
]


@dataclass
class RedactionResult:
    text: str
    redaction_summary: dict[str, int]  # {kind: occurrences}
    redaction_method: str  # "regex" | "dlp"


def redact(text: str) -> RedactionResult:
    summary: dict[str, int] = {}
    out = text
    for kind, pat in _PATTERNS:
        def repl(m: re.Match) -> str:
            summary[kind] = summary.get(kind, 0) + 1
            return f"[REDACTED:{kind}]"
        # CREDIT_CARD pattern can match arbitrary digit runs; only redact if
        # Luhn-valid.
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
