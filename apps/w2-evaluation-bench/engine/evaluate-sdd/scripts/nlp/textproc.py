"""Shared deterministic text primitives for the pre-intelligence layer.

Everything downstream (doc model, evidence locator, registries) builds on
these. Pure stdlib; identical output for identical input, always — that is
what lets the layer live inside a blinded, auditable evaluation pipeline.
"""
from __future__ import annotations
import re

# Function words excluded from content-term matching. Small and curated on
# purpose: an aggressive list starts deleting domain words ("case", "order")
# that Salesforce documents use as nouns.
STOPWORDS = frozenset("""
a an and are as at be been but by can could do does for from had has have how
if in into is it its may might must no not of on or shall should so such that
the their then there these this those to was we were what when where which
will with would you your via any all each per
""".split())

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_\-./]*")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$|^(\d+(?:\.\d+)*)[.)]\s+(\S.*)$")


def tokens(text: str) -> list[str]:
    """Lowercased word tokens, punctuation-stripped, order-preserving."""
    return [m.group(0).lower().strip(".-/") for m in _WORD.finditer(text or "")]


def content_terms(text: str) -> set[str]:
    """The set of judgeable terms: tokens minus stopwords minus 1-char noise."""
    return {t for t in tokens(text) if len(t) > 1 and t not in STOPWORDS}


_LIST_ITEM = re.compile(r"^([-*•|]|\d+[.)])\s")


def sentences(text: str) -> list[str]:
    """Sentence segmentation good enough for evidence snippets: hard-wrapped
    prose lines are re-joined within a paragraph (blank lines and list
    markers start a new block), then split on terminal punctuation followed
    by a capital/paren. Never splits inside an ID like 'SF-1.2'."""
    out: list[str] = []
    buf = ""

    def _flush():
        nonlocal buf
        if buf.strip():
            out.extend(s.strip() for s in _SENT_SPLIT.split(buf.strip()) if s.strip())
        buf = ""

    for line in (text or "").split("\n"):
        ls = line.strip()
        if not ls:
            _flush()
            continue
        if _LIST_ITEM.match(ls):
            _flush()
            buf = ls
            continue
        buf = f"{buf} {ls}" if buf else ls
    _flush()
    return out


def clamp_words(text: str, max_words: int = 25) -> str:
    """First max_words words, verbatim — the exact shape of an evidence
    anchor (<=25 verbatim words per the scoring discipline)."""
    ws = (text or "").split()
    return " ".join(ws[:max_words])


def parse_heading(line: str):
    """(level, title) for markdown '#'-headings and numbered headings
    ('3.2 Data Model'), else None."""
    m = _HEADING.match(line.rstrip())
    if not m:
        return None
    if m.group(1):
        return len(m.group(1)), m.group(2).strip()
    num = m.group(3)
    return num.count(".") + 1, f"{num} {m.group(4).strip()}"
