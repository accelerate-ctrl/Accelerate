"""Hallucination detector.

For each claim with a citation list, check that the cited source's text
contains at least one *salient* token from the claim.  "Salient" =
content word, length ≥4, not in a small stoplist.  Returns a list of
issues with severity_score ∈ [0, 1] (higher = more egregious).

This is intentionally simple + deterministic — it catches the pattern
"the LLM cited source X but X has nothing to do with the claim", which
is the dominant failure mode in dev.  Live mode adds an LLM-judge pass
on top of this in :func:`consultant_loop.adversarial_review`.
"""

from __future__ import annotations

import re
from typing import Any

STOPLIST = {
    "this", "that", "with", "from", "have", "into", "about", "their", "there",
    "which", "while", "would", "could", "should", "where", "when", "what",
    "they", "them", "than", "then", "been", "being", "into", "over", "under",
    "such", "also", "more", "most", "many", "much", "some", "very",
}

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}")


def _salient_tokens(text: str) -> set[str]:
    return {w.lower() for w in WORD_RE.findall(text or "") if w.lower() not in STOPLIST}


def detect_unsupported_claims(claims: list[dict], sources: list[dict]) -> list[dict[str, Any]]:
    by_id = {s.get("id"): s for s in sources}
    issues: list[dict[str, Any]] = []
    for idx, claim in enumerate(claims):
        cs = claim.get("sources") or []
        if not cs:
            issues.append({
                "claim_idx": idx,
                "reason": "no citations",
                "severity_score": 0.9,
                "overlap": 0,
            })
            continue
        ctoks = _salient_tokens(claim.get("text", ""))
        if not ctoks:
            continue
        best_overlap = 0
        for cid in cs:
            src = by_id.get(cid)
            if not src:
                continue
            stoks = _salient_tokens((src.get("text") or "") + " " + (src.get("title") or ""))
            best_overlap = max(best_overlap, len(ctoks & stoks))
        # require at least 2 salient tokens in common; below that = unsupported
        if best_overlap < 2:
            issues.append({
                "claim_idx": idx,
                "reason": f"only {best_overlap} salient token(s) overlap with cited sources",
                "severity_score": 0.5 + 0.2 * (2 - best_overlap),
                "overlap": best_overlap,
            })
    return issues
