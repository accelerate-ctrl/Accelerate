"""Document model: parse a BRD/SDD into a structural map the rest of the
pre-intelligence layer (and the judges, via packet enrichment) can address.

Format-agnostic by design (the components discovery packet already treats
documents as 'numbered sections, capability modules, or distributed prose');
this parser handles markdown headings, numbered headings, and falls back to
one implicit section when a document has no structure at all.
"""
from __future__ import annotations
from .textproc import parse_heading, sentences, content_terms


def build_doc_model(text: str) -> dict:
    """-> {"sections": [{"ref", "title", "level", "text", "word_count",
    "sentences"}], "word_count", "section_count"}. `ref` is the citable
    section reference judges use in `sdd_ref` fields."""
    lines = (text or "").split("\n")
    sections = []
    cur = {"ref": "preamble", "title": "(preamble)", "level": 0, "lines": []}
    n = 0
    for line in lines:
        h = parse_heading(line)
        if h:
            if cur["lines"] or sections:
                sections.append(cur)
            n += 1
            level, title = h
            cur = {"ref": f"§{n} {title}"[:80], "title": title,
                   "level": level, "lines": []}
        else:
            cur["lines"].append(line)
    sections.append(cur)
    out = []
    for s in sections:
        body = "\n".join(s.pop("lines")).strip()
        if not body and s["ref"] == "preamble":
            continue
        sents = sentences(body)
        out.append({**s, "text": body, "word_count": len(body.split()),
                    "sentences": sents})
    return {"sections": out,
            "word_count": sum(s["word_count"] for s in out),
            "section_count": len(out)}


def section_terms(doc: dict) -> list[tuple[dict, set]]:
    """[(section, content-term set)] — cached basis for all matching."""
    return [(s, content_terms(s["title"] + " " + s["text"]))
            for s in doc["sections"]]
