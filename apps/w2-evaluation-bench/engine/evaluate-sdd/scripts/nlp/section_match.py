"""Unsupervised section recognition (learning loop 3): map ANY document's
section headings onto the canonical SDD component vocabulary by TF-IDF
cosine similarity — so "Non-Functional Considerations" is recognized as the
NFR section and "Safeguards & Trust" as Security even though no rule names
those headings. Deterministic, stdlib-only, advisory (the map is packet
enrichment and console context, never a verdict)."""
from __future__ import annotations
import math

from .doc_model import build_doc_model
from .textproc import content_terms

# Canonical component vocabularies (title + the terms that characterize the
# component's content, curated from the workflow's own packets/criteria).
CANONICAL: dict[str, str] = {
    "Scope and Assumptions":
        "scope assumption in-scope out-of-scope boundary constraint premise",
    "Data Model":
        "data model object entity field schema relationship record type "
        "master-detail lookup attribute",
    "Business Process Flows":
        "process flow automation workflow journey approval trigger step "
        "orchestration business",
    "Security and Sharing Model":
        "security sharing permission profile access visibility owd role "
        "encryption compliance safeguard trust fls",
    "Integration Architecture":
        "integration api middleware interface callout external service sync "
        "endpoint credential event messaging",
    "Reporting and Analytics Design":
        "reporting analytics dashboard report kpi metric insight measure "
        "visualization snapshot",
    "Non-Functional Requirements":
        "nfr performance scalability availability reliability latency volume "
        "load throughput capacity concurrent non-functional",
    "Data Migration Approach":
        "migration data-load cutover etl backfill legacy conversion extract "
        "transform seeding",
    "Delivery and Release":
        "delivery release deployment phasing timeline sprint package "
        "environment sandbox rollout",
    "Testing Strategy":
        "testing test uat qa coverage validation defect regression scenario",
}

_CANON_TERMS = {name: content_terms(name + " " + vocab)
                for name, vocab in CANONICAL.items()}
MATCH_THRESHOLD = 1.0  # below this a heading is honestly "unrecognized"


def _fold(ts: set[str]) -> set[str]:
    out = set(ts)
    for t in ts:
        if len(t) > 3 and t.endswith("s"):
            out.add(t[:-1])
    return out


def match_sections(text: str, *, doc: dict | None = None) -> dict:
    """-> {"sections": [{"ref","title","component","score"}],
    "recognized": n} — cosine similarity between each section's term vector
    (title terms triple-weighted; body IDF-weighted) and each canonical
    component vocabulary."""
    d = doc or build_doc_model(text)
    secs = d["sections"]
    n = max(1, len(secs))
    df: dict[str, int] = {}
    sec_terms = []
    for s in secs:
        ts = _fold(content_terms(s["title"] + " " + s["text"]))
        sec_terms.append(ts)
        for t in ts:
            df[t] = df.get(t, 0) + 1
    idf = {t: math.log(n / c) + 1.0 for t, c in df.items()}
    out, hits = [], 0
    for s, ts in zip(secs, sec_terms):
        title_ts = _fold(content_terms(s["title"]))
        best, best_score = None, 0.0
        for name, cts in _CANON_TERMS.items():
            cf = _fold(cts)
            inter = ts & cf
            if not inter:
                continue
            w = sum(idf.get(t, 1.0) * (3.0 if t in title_ts else 1.0)
                    for t in inter)
            denom = math.sqrt(len(ts)) * math.sqrt(len(cf))
            score = w / denom if denom else 0.0
            if score > best_score:
                best, best_score = name, score
        rec = {"ref": s["ref"], "title": s["title"],
               "component": best if best_score >= MATCH_THRESHOLD else None,
               "score": round(best_score, 4)}
        if rec["component"]:
            hits += 1
        out.append(rec)
    return {"sections": out, "recognized": hits, "total": len(secs)}
