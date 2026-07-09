"""Requirement registry: extract the BRD's judgeable requirement inventory.

The BRD is the truth source for requirements (truth-source firewall). The
registry gives Dims 1/2/6 a deterministic backbone: story IDs, modality
statements (shall/must/should), and acceptance criteria — each with the
section it came from, so traceability rows are citable.
"""
from __future__ import annotations
import re
from .doc_model import build_doc_model
from .textproc import clamp_words

# SF-1, US-2.3, REQ-004, NFR-7, AC-1 …
_REQ_ID = re.compile(r"\b((?:SF|US|REQ|NFR|FR|AC)-\d+(?:\.\d+)*)\b", re.I)
_MODAL = re.compile(r"\b(shall|must|should|is required to|needs to)\b", re.I)
_KIND = {"SF": "story", "US": "story", "REQ": "requirement", "FR": "requirement",
         "NFR": "nfr", "AC": "acceptance"}


def extract_requirements(brd_text: str) -> dict:
    """-> {"requirements": [{"id","kind","text","section"}], "counts": {...}}.
    One entry per distinct explicit ID (first statement wins) plus ID-less
    modality statements (id "M-<n>")."""
    doc = build_doc_model(brd_text)
    seen, out, m_n = set(), [], 0
    for sec in doc["sections"]:
        for sent in sec["sentences"]:
            ids = _REQ_ID.findall(sent)
            if ids:
                for rid in ids:
                    rid_u = rid.upper()
                    if rid_u in seen:
                        continue
                    seen.add(rid_u)
                    out.append({"id": rid_u,
                                "kind": _KIND.get(rid_u.split("-")[0], "requirement"),
                                "text": clamp_words(sent, 40),
                                "section": sec["ref"]})
            elif _MODAL.search(sent) and len(sent.split()) >= 5:
                m_n += 1
                out.append({"id": f"M-{m_n}", "kind": "modality",
                            "text": clamp_words(sent, 40),
                            "section": sec["ref"]})
    counts = {}
    for r in out:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    return {"requirements": out, "counts": counts,
            "brd_sections": doc["section_count"]}
