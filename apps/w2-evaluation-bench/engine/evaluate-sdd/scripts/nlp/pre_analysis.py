"""Pre-analysis assembly: one artifact per lane that carries everything the
pre-intelligence layer computed, plus the two consumption surfaces —
prompt_digest() (the advisory block embedded in judgment packets, byte-
identical for both judges) and review_anchor_quality() (the post-judgment
verification that routes weak citations into reconciliation).
"""
from __future__ import annotations
import json
from . import PREINTEL_VERSION
from .doc_model import build_doc_model
from .requirements_registry import extract_requirements
from .lexicon import find_mechanisms
from .evidence_locator import locate_candidates, traceability_matrix, anchor_relevance
from .guardrail_lint import injection_lint, blinding_scan

# Conservative weak-evidence bar: flag ONLY anchors sharing zero judgeable
# terms with the criterion profile, on affirmative verdicts. Low volume by
# design — each flag costs a reconciliation ruling.
WEAK_ANCHOR_THRESHOLD = 0.0


def build_pre_analysis(*, brd_text: str, sdd_text: str,
                       criteria_by_group: dict[str, list[dict]]) -> dict:
    """The lane's full pre-intelligence record. Blinded by construction: it
    reads only the lane-labelled documents; lane identity never appears."""
    doc = build_doc_model(sdd_text)
    reqs = extract_requirements(brd_text)
    candidates = {g: locate_candidates(sdd_text, crits, doc=doc)
                  for g, crits in sorted(criteria_by_group.items())}
    trace = traceability_matrix(reqs["requirements"], sdd_text, doc=doc)
    lint = {"sdd_injection_flags": injection_lint(sdd_text),
            "brd_injection_flags": injection_lint(brd_text),
            "sdd_blinding_tokens": blinding_scan(sdd_text)}
    return {
        "preintel_version": PREINTEL_VERSION,
        "doc": {"sections": [{k: s[k] for k in ("ref", "title", "word_count")}
                             for s in doc["sections"]],
                "word_count": doc["word_count"]},
        "requirements": reqs,
        "mechanisms": find_mechanisms(doc),
        "section_map": __import__("nlp.section_match", fromlist=["match_sections"]).match_sections(sdd_text, doc=doc),
        "evidence": candidates,
        "traceability": trace,
        "guardrail_lint": lint,
        "summary": summarize(candidates, trace, lint),
    }


def summarize(candidates: dict, trace: dict, lint: dict) -> dict:
    cov = [c["coverage"] for c in candidates.values()]
    crit = sum(c["criteria"] for c in cov)
    hits = sum(c["with_candidates"] for c in cov)
    return {"criteria": crit, "criteria_with_candidates": hits,
            "evidence_coverage": round(hits / max(1, crit), 3),
            "requirements_total": trace["total"],
            "requirements_covered": trace["covered"],
            "traceability_rate": trace["rate"],
            "injection_flags": (len(lint["sdd_injection_flags"])
                                + len(lint["brd_injection_flags"])),
            "blinding_tokens_in_input": len(lint["sdd_blinding_tokens"])}


def prompt_digest(pre: dict, group: str, *, max_chars: int = 14000) -> str:
    """The PRE-ANALYSIS advisory block for one dim-group's judgment packets.
    Deterministic, size-bounded (whole criteria dropped from the tail, never
    truncated mid-entry), and explicitly advisory — the instruction hierarchy
    around it is set by the packet prompt."""
    ev = pre["evidence"].get(group, {}).get("per_criterion", {})
    lines = [f"pre-intelligence v{pre['preintel_version']} · advisory retrieval "
             "hints (verify against the SDD; hints are NOT conclusions and may "
             "be incomplete):",
             f"- evidence coverage {pre['summary']['evidence_coverage']:.0%} of "
             f"criteria; BRD traceability {pre['summary']['traceability_rate']:.0%} "
             f"({pre['summary']['requirements_covered']}/{pre['summary']['requirements_total']} requirements located in SDD)"]
    unmatched = [r["id"] for r in pre["traceability"]["rows"]
                 if r["status"] == "unmatched"][:12]
    if unmatched:
        lines.append("- BRD items with NO located SDD coverage (check before "
                     "coding Absent): " + ", ".join(unmatched))
    if pre["guardrail_lint"]["sdd_injection_flags"]:
        lines.append("- CAUTION: instruction-shaped text detected inside the "
                     "SDD (see SECURITY rule): "
                     + "; ".join(f["kind"] for f in
                                 pre["guardrail_lint"]["sdd_injection_flags"][:3]))
    for cid in sorted(ev):
        cands = ev[cid]["candidates"]
        if not cands:
            lines.append(f"[{cid}] no candidate located — document may be "
                         "silent here; verify before coding Absent")
            continue
        for c in cands[:2]:
            lines.append(f"[{cid}] ({c['section']}) \"{c['snippet']}\"")
    out, total = [], 0
    for ln in lines:
        total += len(ln) + 1
        if total > max_chars:
            out.append(f"(+{len(lines) - len(out)} more hints omitted for size)")
            break
        out.append(ln)
    return "\n".join(out)


def review_anchor_quality(cards: dict, diff_criteria: dict,
                          criteria: list[dict]) -> dict:
    """Post-judgment verification, run BETWEEN diff and reconciliation:
    among criteria the judges AGREED on (not already divergent), flag
    affirmative verdicts whose cited anchor shares zero judgeable terms with
    the criterion profile — agreed-but-ungrounded evidence. Flagged items are
    added to the reconcile packet (the intelligent layer confirms with a
    citation or records a dissent); nothing is decided here.

    cards: {judge: scorecard}; -> {cid: {"_reason", "_relevance",
    <judge entries>}} in the reconcile packet's item shape."""
    by_id = {c["id"]: c for c in criteria}
    judges = sorted(cards)
    out = {}
    for cid, c in sorted(by_id.items()):
        if cid in diff_criteria:
            continue  # already going to reconciliation as a divergence
        entries = {j: ((cards[j].get("verdicts") or {}).get(cid) or {})
                   for j in judges}
        v = entries[judges[0]].get("verdict")
        if v not in ("Present", "Partial"):
            continue
        anchor = entries[judges[0]].get("evidence_anchor") or ""
        rel = anchor_relevance(anchor, c)
        if rel <= WEAK_ANCHOR_THRESHOLD:
            out[cid] = {**entries,
                        "_reason": ("advisory weak-evidence check: the agreed "
                                    "anchor shares no judgeable term with this "
                                    "criterion — confirm with a citation or rule"),
                        "_relevance": rel}
    return out


def to_json(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True)
