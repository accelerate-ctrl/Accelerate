#!/usr/bin/env python3
"""source_index_build.py  (Part 2 — foundation for R25b/R25c, content mapping, completeness)

Deterministically parse a BRD or SDD into addressable, hashed segments so that an
evidence_anchor quote can be EXACT-MATCHED against the source (R25b), Absent
findings can record what was actually searched (R25c), and word counts can be
computed from the source rather than trusted from the model (Part 4).

This is the load-bearing prerequisite for evidence verification. It is fully
offline and deterministic: same input -> same index -> same quote_hash.

Segments carry: segment_id, kind (heading|paragraph|bullet|table_cell|footnote),
section path, char_start/char_end (within a normalized full-text), text, and a
normalized-text hash for fuzzy-but-honest matching.

Usage:
  source_index_build.py --input <file.md|.txt|.docx> --doc-id SDD-A --output <index.json>
"""
from __future__ import annotations
import argparse, json, re, hashlib, sys
from pathlib import Path

SCHEMA = "evaluate-sdd-source-index/v1"


def _norm(s: str) -> str:
    """Normalization used for matching: lowercase, collapse whitespace, strip most
    punctuation that varies by typography (smart quotes, dashes). Deterministic."""
    s = s.lower()
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2014", "-").replace("\u2013", "-")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _hash(s: str) -> str:
    return hashlib.sha256(_norm(s).encode("utf-8")).hexdigest()[:16]


def _read_text(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        try:
            from docx import Document
        except ImportError:
            print("python-docx required to read .docx", file=sys.stderr); sys.exit(2)
        d = Document(str(path))
        parts = []
        for p in d.paragraphs:
            parts.append(("para", p.style.name if p.style else "", p.text))
        for t in d.tables:
            for r in t.rows:
                for c in r.cells:
                    parts.append(("cell", "", c.text))
        return parts  # type: ignore
    # text / markdown
    return path.read_text(encoding="utf-8", errors="replace")


def build_index(raw, doc_id: str) -> dict:
    """Build the segment index. `raw` is either a markdown/plain string or a list
    of (kind, style, text) tuples from a .docx."""
    segments = []
    fulltext_parts = []
    cursor = 0
    section_path = []

    def add(kind, text, heading_level=None):
        nonlocal cursor
        text = (text or "").rstrip()
        if not text.strip():
            return
        start = cursor
        fulltext_parts.append(text)
        cursor += len(text) + 1  # +1 for the join newline
        seg = {
            "segment_id": f"{doc_id}-seg-{len(segments)+1:04d}",
            "kind": kind,
            "section_path": list(section_path),
            "char_start": start,
            "char_end": start + len(text),
            "text": text,
            "norm_hash": _hash(text),
            "word_count": len(text.split()),
        }
        segments.append(seg)

    if isinstance(raw, list):  # docx tuples
        for kind, style, text in raw:
            if not text or not text.strip():
                continue
            if kind == "para" and style and style.lower().startswith("heading"):
                lvl = re.sub(r"\D", "", style) or "1"
                section_path = section_path[: int(lvl) - 1] + [text.strip()]
                add("heading", text)
            elif kind == "cell":
                add("table_cell", text)
            else:
                add("paragraph", text)
    else:  # markdown / plain
        for line in raw.splitlines():
            s = line.rstrip()
            if not s.strip():
                continue
            mh = re.match(r"^(#{1,6})\s+(.*)$", s)
            if mh:
                lvl = len(mh.group(1)); title = mh.group(2).strip()
                section_path = section_path[: lvl - 1] + [title]
                add("heading", title)
            elif re.match(r"^\s*[-*+]\s+", s) or re.match(r"^\s*\d+[.)]\s+", s):
                add("bullet", re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", s))
            elif "|" in s and s.count("|") >= 2:
                for cell in [c.strip() for c in s.split("|") if c.strip()]:
                    add("table_cell", cell)
            else:
                add("paragraph", s)

    fulltext = "\n".join(fulltext_parts)
    return {
        "schema": SCHEMA,
        "doc_id": doc_id,
        "sha256": hashlib.sha256(fulltext.encode("utf-8")).hexdigest(),
        "segment_count": len(segments),
        "total_words": sum(s["word_count"] for s in segments),
        "fulltext_norm": _norm(fulltext),
        "segments": segments,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--doc-id", required=True)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    raw = _read_text(args.input)
    idx = build_index(raw, args.doc_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(idx, indent=2), encoding="utf-8")
    print(json.dumps({"doc_id": idx["doc_id"], "segments": idx["segment_count"],
                      "words": idx["total_words"], "sha256": idx["sha256"][:12]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
