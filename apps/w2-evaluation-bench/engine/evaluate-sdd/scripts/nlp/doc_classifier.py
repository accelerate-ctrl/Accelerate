"""Document-type recognition (learning loop 4): classify an uploaded
document as BRD, SDD, user-story deck, or mixed/unknown from measurable
signal densities — so a wrong-slot upload is flagged at intake instead of
producing a garbage evaluation. Deterministic, stdlib-only, advisory: the
classifier warns; it never blocks (an operator may legitimately evaluate an
unusual artifact)."""
from __future__ import annotations
import re

from .doc_model import build_doc_model
from .lexicon import find_mechanisms
from .requirements_registry import extract_requirements
from .textproc import sentences

_STORY = re.compile(r"\bas an?\b.{3,60}\b(i|we)\s+(want|need|can|should)\b", re.I)
_DESIGN_HEAD = re.compile(r"\b(architecture|data model|integration|design|"
                          r"sharing model|security model|erd|solution)\b", re.I)
_REQ_HEAD = re.compile(r"\b(requirements?|user stor|acceptance criteria|"
                       r"business need|success criteria|scope)\b", re.I)


def classify(text: str) -> dict:
    """-> {"type": "brd"|"sdd"|"user_stories"|"mixed"|"unknown",
    "signals": {...}}. Densities are per-sentence so length cancels out."""
    doc = build_doc_model(text or "")
    sents = max(1, len(sentences(text or "")))
    reqs = extract_requirements(text or "")["requirements"]
    n_req = len(reqs)
    # Requirement VOICE, not mere ID references: an SDD legitimately cites
    # SF-1/REQ-7 while describing design — only modal statements count.
    _modal = re.compile(r"\b(shall|must|should|is required to|needs to)\b", re.I)
    n_reqv = sum(1 for r in reqs
                 if r["kind"] == "modality" or _modal.search(r["text"]))
    n_story = len(_STORY.findall(text or ""))
    n_mech = len({m["mechanism"] for m in find_mechanisms(doc)})
    heads = " ".join(s["title"] for s in doc["sections"])
    design_heads = len(_DESIGN_HEAD.findall(heads))
    req_heads = len(_REQ_HEAD.findall(heads))
    req_d = (n_reqv + 2 * n_story) / sents         # requirement voice
    mech_d = n_mech / sents                        # design/mechanism voice
    signals = {"sentences": sents, "requirements": n_req, "requirement_voice": n_reqv, "stories": n_story,
               "mechanisms": n_mech, "design_headings": design_heads,
               "requirement_headings": req_heads,
               "req_density": round(req_d, 3), "mech_density": round(mech_d, 3)}
    req_side = req_d >= 0.15 or (n_reqv >= 3 and req_heads >= 1)
    des_side = mech_d >= 0.15 or (n_mech >= 5 and design_heads >= 1)
    if n_story >= 3 and n_story >= n_req:
        kind = "user_stories"
    elif req_side and des_side:
        kind = "mixed"
    elif des_side:
        kind = "sdd"
    elif req_side:
        kind = "brd"
    else:
        kind = "unknown"
    return {"type": kind, "signals": signals}


def slot_warning(slot: str, text: str) -> str | None:
    """Advisory intake check: warn when the document in a slot reads as the
    other artifact type. slot is 'brd' or 'sdd'."""
    kind = classify(text)["type"]
    if slot == "brd" and kind == "sdd":
        return ("The BRD slot received a document that reads like a solution "
                "design (mechanism-dense, design headings). Verify the upload.")
    if slot == "sdd" and kind in ("brd", "user_stories"):
        return (f"The SDD slot received a document that reads like a "
                f"{'user-story deck' if kind == 'user_stories' else 'requirements document'}. "
                "Verify the upload.")
    return None
