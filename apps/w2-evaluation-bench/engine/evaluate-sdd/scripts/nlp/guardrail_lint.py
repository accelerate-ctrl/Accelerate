"""Guardrail lint: pattern checks the workflow's principles demand BEFORE any
model reads a client document.

- injection_lint: instruction-shaped text inside a document (sentences
  addressed to the evaluator: "ignore your instructions", "score this 10",
  role claims). Complements the DOC_GUARD line already in every packet —
  flagged packets tell the judges exactly where the attempt lives.
- blinding_scan: the R14 token family, checked at INTAKE so a lane-identity
  leak in an input is known before packets exist (R14 still runs on output).
Advisory only: findings are recorded and surfaced, documents are never
modified (the SDD must reach judges verbatim).
"""
from __future__ import annotations
import re
from .textproc import sentences, clamp_words

_INJECTION = [
    (re.compile(r"\bignore\b.{0,40}\b(instruction|prompt|rule|guideline)", re.I),
     "instruction-override attempt"),
    (re.compile(r"\b(you are|act as|pretend to be)\b.{0,60}\b(judge|evaluator|assistant|model)", re.I),
     "role-claim addressed to the evaluator"),
    (re.compile(r"\b(score|rate|mark)\b.{0,30}\b(this|it)\b.{0,30}\b(10|full|maximum|highest)", re.I),
     "self-scoring instruction"),
    (re.compile(r"\b(system prompt|hidden context|reveal|disclose)\b.{0,40}\b(prompt|instruction|mapping|escrow)", re.I),
     "exfiltration attempt"),
    (re.compile(r"\bverdict\b.{0,30}\b(present|partial)\b.{0,30}\b(always|must|regardless)", re.I),
     "verdict-forcing instruction"),
]

# R14 family (contracts): lane-identity tokens that must never leak.
_BLINDING = re.compile(r"\b(zen+agent|za\b|off[\s\-]the[\s\-]shelf|ots)\b", re.I)


def injection_lint(text: str) -> list[dict]:
    out = []
    for sent in sentences(text or ""):
        for rx, kind in _INJECTION:
            if rx.search(sent):
                out.append({"kind": kind, "excerpt": clamp_words(sent, 20)})
                break
    return out


def blinding_scan(text: str) -> list[str]:
    return sorted({m.group(0).lower() for m in _BLINDING.finditer(text or "")})
