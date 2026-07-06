#!/usr/bin/env python3
"""evidence_anchor_verify.py  (Part 2 — R25b/R25c/R25d/R25e)

Verify that an evidence_anchor is actually grounded in the source document, and
SEPARATE two questions the system previously conflated:

  quote_exists          — is this text actually in the SDD? (deterministic, R25b)
  quote_supports_verdict — does that text actually demonstrate the criterion?
                           (yes/partial/no, R25e — relevance, not just presence)

A real-but-irrelevant quote must NOT pass as sufficient evidence. Absent findings
must carry negative_evidence describing what was searched (R25c).

This module is deterministic for quote_exists (string/normalized match against the
source index). quote_supports_verdict is a structured judgement the model supplies
and this module sanity-checks for completeness — it never fabricates relevance.

Usage (library):
  from evidence_anchor_verify import verify_anchor
  verify_anchor(anchor, verdict, source_index, depth_indicator_components)
"""
from __future__ import annotations
import re, hashlib, json, argparse, sys
from pathlib import Path

SCHEMA = "evaluate-sdd-evidence-verification/v1"


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2014", "-").replace("\u2013", "-")
    return re.sub(r"\s+", " ", s).strip()


def quote_exists(anchor: str, source_index: dict) -> dict:
    """Deterministic R25b. Returns match detail. Exact normalized substring match
    against the source fulltext is the strong signal; a high token-overlap against
    any single segment is an 'approved normalized match' (handles trivial
    re-typing) but is flagged as normalized, not exact."""
    na = _norm(anchor)
    if not na or len(na) < 4:
        return {"quote_exists": False, "match_type": "none", "reason": "anchor empty/too short"}
    full = source_index.get("fulltext_norm", "")
    if na in full:
        return {"quote_exists": True, "match_type": "exact"}
    # token-overlap fallback against best segment (normalized match)
    atoks = set(na.split())
    best = (0.0, None)
    for seg in source_index.get("segments", []):
        stoks = set(_norm(seg["text"]).split())
        if not stoks:
            continue
        overlap = len(atoks & stoks) / max(1, len(atoks))
        if overlap > best[0]:
            best = (overlap, seg["segment_id"])
    if best[0] >= 0.85:
        return {"quote_exists": True, "match_type": "normalized",
                "matched_segment": best[1], "overlap": round(best[0], 2)}
    return {"quote_exists": False, "match_type": "none",
            "best_overlap": round(best[0], 2), "best_segment": best[1]}


def supports_verdict(anchor: str, verdict: str, depth_components: list) -> dict:
    """R25e relevance check. Deterministic component-coverage signal: how many of
    the criterion's depth_indicator components are textually present in the anchor.
    This does not 'prove' architectural correctness — it flags real-but-irrelevant
    quotes (zero component overlap) so they cannot pass as sufficient evidence."""
    na = _norm(anchor)
    comps = depth_components or []
    hit, missing = [], []
    for c in comps:
        # a component is 'addressed' if any of its content words appears in the anchor
        cwords = [w for w in _norm(c).split() if len(w) > 3]
        if cwords and any(w in na for w in cwords):
            hit.append(c)
        else:
            missing.append(c)
    if not comps:
        # no decomposed bar to check against; fall back to 'not assessable here'
        return {"quote_supports_verdict": "not_assessable",
                "support_rationale": "criterion has no depth components to check relevance against",
                "missing_depth_indicator_components": []}
    frac = len(hit) / len(comps)
    if verdict in ("Present", "Partial"):
        status = "yes" if frac >= 0.5 else ("partial" if frac > 0 else "no")
    else:
        status = "not_applicable"
    return {
        "quote_supports_verdict": status,
        "support_rationale": f"{len(hit)}/{len(comps)} depth components textually present in anchor",
        "components_present": hit,
        "missing_depth_indicator_components": missing,
    }


def verify_anchor(anchor: str, verdict: str, source_index: dict,
                  depth_components: list = None,
                  negative_evidence: dict = None) -> dict:
    """Full R25b–R25e verification for one citation."""
    v = (verdict or "").strip()
    result = {"schema": SCHEMA, "verdict": v}
    if v in ("Absent",):
        # R25c: Absent needs negative_evidence, not a quote.
        ne = negative_evidence or {}
        ok = bool(ne.get("searched_sections") and ne.get("searched_terms"))
        result.update({
            "status": "verified_absent" if ok else "unverified_absent",
            "quote_exists": None,
            "negative_evidence_ok": ok,
            "reason": None if ok else "Absent finding missing negative_evidence (searched_sections + searched_terms required)",
        })
        return result
    if v == "NA":
        result.update({"status": "not_applicable", "quote_exists": None})
        return result
    # Present / Partial: must exist AND support
    qe = quote_exists(anchor, source_index)
    sv = supports_verdict(anchor, verdict, depth_components or [])
    exists = qe.get("quote_exists", False)
    supports = sv.get("quote_supports_verdict")
    if not exists:
        status = "fabricated_or_unmatched"   # R25b failure: not in source
    elif supports == "no":
        status = "irrelevant_quote"          # R25e failure: real but off-target
    elif qe.get("match_type") == "normalized" or supports == "partial":
        status = "verified_weak"
    else:
        status = "verified"
    result.update({"status": status, **qe, **sv})
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--citations", required=True, type=Path,
                    help="JSON list of {anchor,verdict,depth_components?,negative_evidence?}")
    ap.add_argument("--source-index", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    si = json.loads(args.source_index.read_text())
    cites = json.loads(args.citations.read_text())
    out = [verify_anchor(c.get("anchor", ""), c.get("verdict", ""), si,
                         c.get("depth_components"), c.get("negative_evidence")) for c in cites]
    verified = sum(1 for r in out if r["status"] in ("verified", "verified_weak", "verified_absent"))
    rep = {"schema": SCHEMA, "total": len(out), "verified": verified,
           "verification_rate": round(verified / max(1, len(out)), 3), "results": out}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps({"total": len(out), "verified": verified,
                      "rate": rep["verification_rate"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
