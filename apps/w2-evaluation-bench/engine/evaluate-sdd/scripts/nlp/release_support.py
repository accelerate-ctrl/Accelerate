"""Release-crosswalk support: the pre-intelligence layer around the ONE
web-facing act of judgment (the live release-evidence packet).

Two jobs, same covenant (prepare and verify, never judge):

- enrich_queries: after the engine's crosswalk extract, add deterministic
  high-precision search variants per mechanism (Salesforce-controlled-domain
  scoped, release-notes phrasing, API-version pinned) plus the SDD sections
  where the mechanism appears. Additive fields only — the engine's resolve
  step reads its own fields and is untouched; the evidence packet embeds the
  enriched records verbatim, so the web-searching judge gets sharper targets.

- review_evidence: after the web results come back, score each snippet's
  lexical relevance to its mechanism and pre-check the R23 domain rule
  (only *.salesforce.com may assert a status). Findings are ADVISORY: a
  separate review artifact + digest counts; nothing is dropped or rewritten
  — the R23 validator remains the enforcement point.
"""
from __future__ import annotations
from urllib.parse import urlparse

from .textproc import content_terms

SF_DOMAIN_SUFFIX = ".salesforce.com"


def _domain_ok(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host == "salesforce.com" or host.endswith(SF_DOMAIN_SUFFIX)


def enrich_queries(queries: list[dict]) -> list[dict]:
    """Add `nlp_variants` (deterministic, ordered, deduped) to each crosswalk
    query record. Original fields are preserved byte-for-byte."""
    out = []
    for q in queries:
        name = (q.get("mechanism_name") or q.get("mechanism_key") or "").strip()
        if not name:
            out.append(dict(q))
            continue
        variants = [
            f'"{name}" site:help.salesforce.com',
            f'"{name}" Salesforce release notes',
            f'"{name}" site:developer.salesforce.com',
            f'"{name}" retirement OR deprecated OR end-of-life Salesforce',
        ]
        for v in (q.get("api_versions") or [])[:2]:
            variants.append(f'"{name}" API version {v} Salesforce')
        sections = sorted({(m.get("section") or "").strip()
                           for m in (q.get("mentions") or []) if m.get("section")})
        rec = dict(q)
        rec["nlp_variants"] = variants
        if sections:
            rec["sdd_sections"] = sections[:4]
        out.append(rec)
    return out


def snippet_relevance(snippet: str, mechanism_name: str) -> float:
    """Share of the mechanism's content terms present in the snippet.
    1.0 = every term of the mechanism name appears; 0.0 = none do."""
    mts = content_terms(mechanism_name)
    if not mts:
        return 0.0
    sts = content_terms(snippet or "")
    return round(len(mts & sts) / len(mts), 4)


def review_evidence(evidence: dict, queries: list[dict]) -> dict:
    """Advisory review of a live-evidence result: per-mechanism relevance and
    domain pre-checks. -> {"per_mechanism": {...}, "summary": {...}}."""
    names = {q.get("mechanism_key"): (q.get("mechanism_name") or "")
             for q in queries}
    per, weak, offdomain, total = {}, 0, 0, 0
    for key, items in sorted((evidence or {}).items()):
        name = names.get(key, key)
        rows = []
        for it in (items or []):
            total += 1
            rel = snippet_relevance(
                f"{it.get('title') or ''} {it.get('snippet') or ''}", name)
            dom = _domain_ok(it.get("url") or "")
            if rel == 0.0:
                weak += 1
            if not dom:
                offdomain += 1
            rows.append({"url": it.get("url"), "relevance": rel,
                         "salesforce_domain": dom})
        per[key] = {"mechanism": name, "items": rows,
                    "found": len(rows),
                    "weak": sum(1 for r in rows if r["relevance"] == 0.0)}
    return {"per_mechanism": per,
            "summary": {"mechanisms": len(per), "items": total,
                        "low_relevance_items": weak,
                        "non_salesforce_domain_items": offdomain}}
