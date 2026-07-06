#!/usr/bin/env python3
"""_completeness_layer.py  (Parts 3,5,7,8,9,10,11 — the Completeness & Adaptability Layer)

ARCHIVAL (v4.6): not invoked by the batch pipeline; retained for lineage. See
references/refinement-v4.3-completeness-layer.md.

A single deterministic module exposing the layer's functions. Kept in one file to
limit surface area and import overhead; each function is independently testable and
CLI-exposed via thin wrappers. All FACTS (platform currency, licensing) are resolved
elsewhere via the Salesforce-source path; this module holds detection + routing LOGIC
only, loaded from registries that do not store stale facts.
"""
from __future__ import annotations
import json, re, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "registries"


def _load(p):
    return json.loads((REG / p).read_text())


# ---------- Part 3/9: domain profile detection ----------
def detect_domains(text: str) -> dict:
    man = _load("domain_profiles/manifest.json")
    t = (text or "").lower()
    detected = []
    for entry in man["profiles"]:
        prof = _load(f"domain_profiles/{entry['file']}")
        req = prof["signals"]["required_terms"]; opt = prof["signals"]["optional_terms"]
        if not req and not opt:
            continue
        req_hits = [w for w in req if w in t]
        opt_hits = [w for w in opt if w in t]
        if req_hits:
            conf = min(1.0, 0.5 + 0.15 * len(req_hits) + 0.05 * len(opt_hits))
            detected.append({"profile_id": prof["profile_id"], "confidence": round(conf, 2),
                             "required_hits": req_hits, "optional_hits": opt_hits,
                             "expected_design_areas": prof["expected_design_areas"]})
    detected.sort(key=lambda d: -d["confidence"])
    status = "known_domain" if detected and detected[0]["confidence"] >= 0.5 else \
             ("emerging" if detected else "unknown")
    return {"schema": "domain-detect/v1", "detected_profiles": detected,
            "profile_status": status}


# ---------- Part 10: OOD detection (with abstention; weak != OOD) ----------
def detect_ood(domain_result: dict, benchmark_coverage: float,
               extraction_coverage: float, applicable_criteria: int,
               labeled_criteria: int) -> dict:
    th = _load("ood/ood_thresholds.json")["thresholds"]
    reasons, score = [], 0.0
    top_conf = domain_result["detected_profiles"][0]["confidence"] if domain_result.get("detected_profiles") else 0.0
    if top_conf <= th["out_of_distribution_max_domain_confidence"]:
        reasons.append({"type": "domain_gap", "detail": f"top domain confidence {top_conf} <= {th['out_of_distribution_max_domain_confidence']}"}); score += 0.4
    if benchmark_coverage < th["in_distribution_min_benchmark_coverage"]:
        reasons.append({"type": "benchmark_gap", "detail": f"only {labeled_criteria}/{applicable_criteria} applicable criteria have benchmark labels"}); score += 0.3
    if extraction_coverage < th["not_assessable_max_extraction_coverage"]:
        return {"schema": "ood-result/v1", "ood_status": "not_assessable", "ood_score": 1.0,
                "ood_reasons": reasons + [{"type": "source_gap", "detail": f"extraction coverage {extraction_coverage} too low to assess"}],
                "allowed_actions": ["request_corrected_inputs", "request_sa_context"]}
    if score >= 0.6:
        st = "out_of_distribution"
    elif score >= 0.3:
        st = "near_distribution"
    else:
        st = "in_distribution"
    return {"schema": "ood-result/v1", "ood_status": st, "ood_score": round(score, 2),
            "ood_reasons": reasons,
            "allowed_actions": {"in_distribution": ["proceed"],
                                "near_distribution": ["proceed_advisory"],
                                "out_of_distribution": ["proceed_advisory", "request_sa_context", "exclude_from_lift_claims", "create_domain_profile"]}[st],
            "note": "A weak in-domain SDD is NOT OOD; this reflects calibration-domain fit, not SDD quality."}


# ---------- Part 7: org context ----------
def validate_org_context(oc: dict) -> dict:
    if not oc:
        return {"schema": "org-context/v1", "org_context_status": "absent",
                "confirmed_constraints": [], "unknown_constraints": ["all org-specific feasibility unknown"],
                "assessment_impact": [{"area": "feasibility", "impact": "org-specific feasibility not confirmed"}]}
    org = oc.get("salesforce_org", {})
    confirmed = [f"{c} licensed" for c in org.get("clouds_licensed", [])]
    confirmed += [f"{f} enabled" for f in org.get("features_enabled", [])]
    unknown = [f"{f} unknown" for f in org.get("features_unknown", [])]
    status = "provided_partial" if unknown else ("provided_full" if confirmed else "absent")
    return {"schema": "org-context/v1", "org_context_status": status,
            "confirmed_constraints": confirmed, "unknown_constraints": unknown,
            "assessment_impact": [{"area": "licensing", "impact": f"{u}"} for u in unknown]}


# ---------- Part 8: feasibility (taxonomy + routing; facts come live) ----------
def assess_feasibility(mechanism: str, sdd_quote: str, release_status: str,
                       org_context_result: dict) -> dict:
    logic = _load("feasibility/feasibility_logic.json")
    confirmed = " ".join(org_context_result.get("confirmed_constraints", [])).lower()
    unknown = " ".join(org_context_result.get("unknown_constraints", [])).lower()
    m = mechanism.lower()
    if m in confirmed:
        lic = "confirmed"
    elif m in unknown or org_context_result.get("org_context_status") == "absent":
        lic = "unknown"
    else:
        lic = "unstated"
    if release_status in ("retired", "end_of_support", "superseded"):
        st = "NOT_FEASIBLE"
    elif lic == "confirmed":
        st = "CONFIRMED_FEASIBLE"
    elif lic == "unknown":
        st = "SA_CONFIRMATION_REQUIRED"
    else:
        st = "PLAUSIBLE_UNCONFIRMED"
    return {"mechanism": mechanism, "sdd_quote": sdd_quote, "release_status": release_status,
            "license_status": lic, "feasibility_status": st,
            "recommendation": ("Confirm licensing/enablement before treating as build-ready"
                               if st in ("SA_CONFIRMATION_REQUIRED", "PLAUSIBLE_UNCONFIRMED") else
                               "Replace: not in force" if st == "NOT_FEASIBLE" else "OK")}


# ---------- Part 3/7: clarification queue ----------
def build_clarifications(brd_gaps: list, feasibility_findings: list) -> dict:
    pats = _load("clarification/ambiguity_patterns.json")["patterns"]
    by_id = {p["id"]: p for p in pats}
    qs = []
    for g in brd_gaps or []:
        p = by_id.get(g.get("pattern_id"), {})
        qs.append({"question_id": f"CQ-{len(qs)+1:03d}", "priority": p.get("severity", "Medium"),
                   "asked_of": "Client / Product Owner", "area": p.get("area", g.get("area", "BRD")),
                   "question": g.get("question", ""), "why_needed": g.get("why", ""),
                   "affected_zms_refs": g.get("zms_refs", []),
                   "if_unanswered": g.get("if_unanswered", "mark area not assessable")})
    for f in feasibility_findings or []:
        if f.get("feasibility_status") == "SA_CONFIRMATION_REQUIRED":
            qs.append({"question_id": f"CQ-{len(qs)+1:03d}", "priority": "High", "asked_of": "SA / Admin",
                       "area": "Feasibility", "question": f"Confirm licensing/enablement for {f['mechanism']}.",
                       "why_needed": "Feature is current but org availability unconfirmed.",
                       "affected_zms_refs": ["3"], "if_unanswered": "mark feasibility not confirmed"})
    blocking = any(q["priority"] == "Blocking" for q in qs)
    return {"schema": "clarification-queue/v1",
            "clarification_status": "blocking" if blocking else ("non_blocking" if qs else "none"),
            "questions": qs}


# ---------- Part 11: completeness profile + Review Completeness Level ----------
def build_completeness(inputs: dict) -> dict:
    """inputs: brd_complete(bool), extraction_coverage(0-1), zms_coverage(0-1),
    evidence_verification_rate(0-1), benchmark_coverage(0-1), domain_confidence(0-1),
    ood_status(str), org_context_status(str), feasibility_assessed(bool),
    release_coverage(0-1), blocking_clarifications(int)."""
    i = inputs
    reasons = []
    score = 0
    def add(cond, pts, msg):
        nonlocal score
        if cond: score += pts; reasons.append(msg)
    add(i.get("extraction_coverage", 0) >= 0.8, 1, "SDD text extraction complete")
    add(i.get("brd_complete"), 1, "BRD requirements extracted")
    add(i.get("evidence_verification_rate", 0) >= 0.9, 1, f"Evidence verification {int(i.get('evidence_verification_rate',0)*100)}%")
    add(i.get("zms_coverage", 0) >= 0.6, 1, "ZMS applicable-criteria coverage adequate")
    add(i.get("benchmark_coverage", 0) >= 0.5, 1, "Benchmark covers majority of applicable criteria")
    add(i.get("domain_confidence", 0) >= 0.5, 1, "Domain profile detected with confidence")
    if i.get("ood_status") == "not_assessable":
        level, label = "C0", "Not assessable"
    elif i.get("ood_status") == "out_of_distribution":
        level, label = "C1", "Minimal completeness"
    else:
        level = {0:"C1",1:"C1",2:"C2",3:"C3",4:"C3",5:"C4",6:"C4"}.get(score, "C4")
        # C5 reserved: requires human-validated benchmark, which we honestly never have here
        label = {"C1":"Minimal completeness","C2":"Partial completeness","C3":"Reviewable with caveats",
                 "C4":"Micro-calibrated complete"}[level]
    if i.get("org_context_status") in (None, "absent"):
        reasons.append("Org licensing context missing")
    if i.get("blocking_clarifications", 0) > 0:
        reasons.append(f"{i['blocking_clarifications']} blocking client clarification(s) remain")
    impact = ("Build-readiness verdict should be treated as advisory until the items above are confirmed."
              if level in ("C0", "C1", "C2", "C3") else
              "Review basis is micro-calibrated; still not a substitute for full SA adjudication.")
    return {"schema": "completeness-profile/v1",
            "review_completeness": {"level": level, "label": label, "reasons": reasons, "impact": impact},
            "note": "Measures evaluation COVERAGE/reliability, not SDD quality. C5 (production-complete) is unreachable without human-validated benchmark labels — by design."}
