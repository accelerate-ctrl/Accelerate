"""Evidence locator — the core pattern recognizer of the pre-intelligence
layer.

For every ZMS criterion it builds a lexical profile from the calibration's
own language (criterion name + depth_indicator + depth_indicator_components,
plus a curated synonym expansion), then ranks the SDD's sentences by
IDF-weighted term overlap and emits candidate evidence spans in exactly the
shape a judge must cite: verbatim <=25-word snippets with a section ref.

Statistical NLP, fully deterministic: same documents + same calibration =>
same candidates, byte for byte. Candidates are ADVISORY retrieval hints —
the judges verify them against the full SDD, which stays in every packet.
"""
from __future__ import annotations
import math
from .doc_model import build_doc_model
from .textproc import content_terms, clamp_words

# Domain synonym expansion: calibration language -> SDD language. Small and
# curated; every entry is a pattern the workflow's principles actually score.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "object": ("entity", "sobject", "table"),
    "api": ("endpoint", "rest", "soap", "callout"),
    "security": ("sharing", "fls", "crud", "permission", "profile", "owd"),
    "encryption": ("shield", "encrypted", "tls", "at-rest"),
    "integration": ("middleware", "mulesoft", "interface", "sync", "callout"),
    "automation": ("flow", "trigger", "apex", "workflow", "process"),
    "requirement": ("story", "capability", "user-story", "scope"),
    "migration": ("etl", "data-load", "cutover", "backfill"),
    "assumption": ("constraint", "dependency", "prerequisite", "risk"),
    "test": ("uat", "coverage", "unit-test", "validation"),
    "report": ("dashboard", "analytics", "kpi", "metric"),
    "estimate": ("effort", "sizing", "timeline", "phase", "sprint"),
    "governance": ("runbook", "monitoring", "observability", "alerting"),
    "decision": ("rationale", "trade-off", "alternative", "option"),
}


def criterion_profile(criterion: dict) -> set[str]:
    """Content-term profile of one ZMS criterion, synonym-expanded."""
    base = " ".join([criterion.get("name", ""),
                     criterion.get("depth_indicator", ""),
                     " ".join(criterion.get("depth_indicator_components") or []),
                     criterion.get("parent_sub_criterion_name", "")])
    terms = content_terms(base)
    for t in list(terms):
        terms.update(SYNONYMS.get(t, ()))
    return terms


def _idf(doc_sentences: list[tuple[str, str, set]]) -> dict[str, float]:
    n = max(1, len(doc_sentences))
    df: dict[str, int] = {}
    for _, _, ts in doc_sentences:
        for t in ts:
            df[t] = df.get(t, 0) + 1
    return {t: math.log(n / d) + 1.0 for t, d in df.items()}


def _doc_sentences(doc: dict) -> list[tuple[str, str, set]]:
    out = []
    for sec in doc["sections"]:
        for s in sec["sentences"]:
            ts = content_terms(s)
            if ts:
                out.append((s, sec["ref"], ts))
    return out


def locate_candidates(sdd_text: str, criteria: list[dict], *, top_k: int = 3,
                      doc: dict | None = None) -> dict:
    """-> {"per_criterion": {cid: {"candidates": [{"snippet","section",
    "score"}], "profile_size": n}}, "coverage": {...}}. A criterion with no
    sentence sharing >=2 profile terms gets an empty candidate list — an
    honest 'the document may be silent here' signal, never a verdict."""
    d = doc or build_doc_model(sdd_text)
    sents = _doc_sentences(d)
    idf = _idf(sents)
    per, with_hits = {}, 0
    for c in criteria:
        prof = criterion_profile(c)
        scored = []
        for s, ref, ts in sents:
            hit = prof & ts
            if len(hit) < 2:
                continue
            score = sum(idf.get(t, 1.0) for t in hit) / math.sqrt(len(ts))
            scored.append((round(score, 4), s, ref, len(hit)))
        scored.sort(key=lambda x: (-x[0], x[2], x[1]))
        cands = [{"snippet": clamp_words(s), "section": ref,
                  "score": sc, "matched_terms": h}
                 for sc, s, ref, h in scored[:top_k]]
        if cands:
            with_hits += 1
        per[c["id"]] = {"candidates": cands, "profile_size": len(prof)}
    n = max(1, len(criteria))
    return {"per_criterion": per,
            "coverage": {"criteria": len(criteria), "with_candidates": with_hits,
                         "rate": round(with_hits / n, 3)}}


def anchor_relevance(anchor: str, criterion: dict) -> float:
    """Post-judgment verification: how much of the cited anchor's content
    overlaps the criterion's profile. 0.0 == the anchor shares no judgeable
    term with what the criterion measures (the conservative weak-evidence
    flag); higher is better. Advisory — routed to reconciliation, never
    applied as a score."""
    ts = content_terms(anchor)
    if not ts:
        return 0.0
    prof = criterion_profile(criterion)
    return round(len(ts & prof) / len(ts), 4)


def traceability_matrix(requirements: list[dict], sdd_text: str,
                        doc: dict | None = None) -> dict:
    """BRD requirement -> SDD coverage pre-map (Dims 1/2/6 backbone).
    A requirement is 'referenced' when its ID appears verbatim in the SDD,
    'addressed' when some SDD section shares >=40% of its content terms,
    else 'unmatched' (a gap candidate for the judges, not a verdict)."""
    d = doc or build_doc_model(sdd_text)
    low = sdd_text.lower()
    sec_terms = [(s["ref"], content_terms(s["title"] + " " + s["text"]))
                 for s in d["sections"]]
    rows, hit = [], 0
    for r in requirements:
        rid = r["id"]
        if not rid.startswith("M-") and rid.lower() in low:
            rows.append({"id": rid, "status": "referenced", "sdd_section": None})
            hit += 1
            continue
        rts = content_terms(r["text"])
        best_ref, best = None, 0.0
        for ref, ts in sec_terms:
            if not rts:
                break
            ov = len(rts & ts) / len(rts)
            if ov > best:
                best, best_ref = ov, ref
        if best >= 0.4:
            rows.append({"id": rid, "status": "addressed", "sdd_section": best_ref,
                         "overlap": round(best, 3)})
            hit += 1
        else:
            rows.append({"id": rid, "status": "unmatched", "sdd_section": None})
    n = max(1, len(rows))
    return {"rows": rows, "covered": hit, "total": len(rows),
            "rate": round(hit / n, 3)}
