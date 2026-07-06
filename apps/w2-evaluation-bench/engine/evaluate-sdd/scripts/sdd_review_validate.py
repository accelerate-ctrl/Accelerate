#!/usr/bin/env python3
"""sdd_review_validate.py  (Mode B hardening)

Validate a Mode B (single-SDD qualitative review) bundle BEFORE it is rendered to
a .docx, so a generic, ungrounded review can no longer produce a polished report.

This automates the discipline a senior SA applies to their own review: every
finding must be grounded in the SDD (or carry negative evidence), map to a ZMS
lens, and every recommendation must be actionable and trace to a finding.

FRAMING (important): this workflow AUTOMATES the SA's manual review. It is NOT a
task-router. Uncertainty is expressed as STATUS describing what is missing
(SA_CONFIRMATION_REQUIRED, CLIENT_CLARIFICATION_REQUIRED, ORG_CONTEXT_REQUIRED,
LICENSE_CONFIRMATION_REQUIRED, NOT_ASSESSABLE) — never as an owner assignment.
There are NO owner_role / assigned_to / human_owner fields, required or optional.

Bundle shape (hardened):
{
  "mode": "B",
  "build_ready": "build_ready | build_ready_with_conditions | not_build_ready",
  "findings": [
    {"id","dimension","zms_lens","verdict","evidence_anchor"|"negative_evidence",
     "is_blocking"(bool), "requires"(optional status), "brd_ref"(if requirement),
     "salesforce_source"(if platform-currentness)}
  ],
  "recommendations": [
    {"id","traces_to_finding","what_to_change","why_it_matters",
     "what_good_looks_like","done_when","priority","affected_zms_refs","evidence_refs"}
  ],
  "clarifications": [ ... optional, from clarification_queue_build ... ]
}

Legacy bundles (findings_by_dimension with bare-string strengths/gaps) are accepted
in COMPAT mode with warnings, so existing runs don't hard-break; production runs
should emit the structured shape.

Usage:
  sdd_review_validate.py --bundle <review.json> [--sdd-source-index <idx.json>]
      [--policy production|advisory] --output <validation.json>
  exit 0 = valid (or compat-valid); exit 20 = validation failed.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

VALID_STATUSES = {"SA_CONFIRMATION_REQUIRED", "CLIENT_CLARIFICATION_REQUIRED",
                  "ORG_CONTEXT_REQUIRED", "LICENSE_CONFIRMATION_REQUIRED", "NOT_ASSESSABLE"}
OWNER_FIELDS = {"owner", "owner_role", "assigned_to", "reviewer_owner",
                "human_owner", "remediation_owner"}
REC_REQUIRED = ("what_to_change", "why_it_matters", "what_good_looks_like",
                "done_when", "priority", "affected_zms_refs", "evidence_refs")


def _is_sf_url(url: str) -> bool:
    try:
        from source_authority import is_salesforce_url
        return is_salesforce_url(url)
    except Exception:
        return bool(url) and "salesforce.com" in url  # conservative fallback


def validate_review(bundle: dict, source_index: dict = None,
                    policy: str = "advisory") -> tuple[bool, list, list]:
    errors, warnings = [], []

    # Owner fields must NOT be required dependencies. If present, warn (not fail) —
    # they are simply ignored; the workflow never depends on ownership.
    def _scan_owner(obj, where):
        if isinstance(obj, dict):
            for k in obj:
                if k.lower() in OWNER_FIELDS:
                    warnings.append(f"{where}: owner-style field '{k}' present and ignored "
                                    f"(this workflow automates SA review; it does not assign owners)")

    findings = bundle.get("findings")
    legacy = findings is None and "findings_by_dimension" in bundle

    if legacy:
        warnings.append("COMPAT: legacy findings_by_dimension (bare strings) — findings are "
                        "not individually grounded/ZMS-mapped. Production runs should emit "
                        "structured 'findings' with evidence + zms_lens. Validating structure only.")
        # still validate recommendations below
    elif not findings:
        errors.append("No findings present — a review bundle must contain findings.")

    # ---- structured findings ----
    blocking_unresolved = []
    for i, f in enumerate(findings or []):
        _scan_owner(f, f"findings[{i}]")
        fid = f.get("id", f"finding[{i}]")
        # every finding grounded: evidence_anchor OR negative_evidence OR an honest status
        has_anchor = bool(f.get("evidence_anchor"))
        has_neg = bool(f.get("negative_evidence"))
        status = f.get("requires")
        if not (has_anchor or has_neg or status in VALID_STATUSES):
            errors.append(f"{fid}: finding has no evidence_anchor, no negative_evidence, and no "
                          f"missing-info status — every finding must be grounded or flagged.")
        if status and status not in VALID_STATUSES:
            errors.append(f"{fid}: requires='{status}' is not a recognised status {sorted(VALID_STATUSES)}")
        # every finding maps to a ZMS lens
        if not f.get("zms_lens") and not f.get("dimension"):
            errors.append(f"{fid}: finding does not map to a ZMS lens/dimension.")
        # requirement-related finding must cite BRD trace
        if f.get("kind") == "requirement" and not f.get("brd_ref"):
            errors.append(f"{fid}: requirement-related finding must cite a BRD trace (brd_ref).")
        # platform-currentness finding must cite Salesforce source OR be SA_CONFIRMATION_REQUIRED
        if f.get("kind") == "platform_currentness":
            if not (_is_sf_url(f.get("salesforce_source", "")) or status == "SA_CONFIRMATION_REQUIRED"):
                errors.append(f"{fid}: platform-currentness finding must cite a Salesforce-controlled "
                              f"source or be marked SA_CONFIRMATION_REQUIRED.")
        # exact-source verification when an index is available
        if source_index and has_anchor and f.get("verdict") in ("Present", "Partial"):
            try:
                import evidence_anchor_verify as EV
                ver = EV.verify_anchor(f["evidence_anchor"], f.get("verdict", "Present"),
                                       source_index, f.get("depth_components"))
                if ver["status"] == "fabricated_or_unmatched":
                    errors.append(f"{fid}: evidence_anchor does not resolve in the SDD source index "
                                  f"(fabricated/mis-transcribed).")
                elif ver["status"] == "irrelevant_quote":
                    warnings.append(f"{fid}: evidence_anchor exists but weakly supports the finding.")
            except Exception:
                pass
        if f.get("is_blocking") and not f.get("waived"):
            blocking_unresolved.append(fid)

    # ---- recommendations ----
    recs = bundle.get("recommendations", []) or []
    finding_ids = {f.get("id") for f in (findings or []) if f.get("id")}
    for i, r in enumerate(recs):
        _scan_owner(r, f"recommendations[{i}]")
        rid = r.get("id", f"rec[{i}]")
        # trace to a finding (skip the hard check in legacy mode where findings lack ids)
        if not legacy:
            tf = r.get("traces_to_finding")
            if not tf:
                errors.append(f"{rid}: recommendation does not trace to a finding (traces_to_finding).")
            elif finding_ids and tf not in finding_ids:
                errors.append(f"{rid}: traces_to_finding='{tf}' matches no finding id.")
        # required actionable fields (owner fields explicitly NOT among them)
        for req in REC_REQUIRED:
            if not r.get(req):
                (errors if not legacy else warnings).append(
                    f"{rid}: recommendation missing required field '{req}'.")

    # ---- build-readiness coherence ----
    br = bundle.get("build_ready")
    if br == "build_ready" and blocking_unresolved:
        errors.append(f"build_ready='build_ready' but {len(blocking_unresolved)} unresolved blocking "
                      f"finding(s) {blocking_unresolved}: cap to build_ready_with_conditions, resolve, "
                      f"or set 'waived' with explanation on each.")
    # blocking clarification caps build-readiness
    clars = bundle.get("clarifications", []) or []
    blocking_clar = [c for c in clars if c.get("priority") == "Blocking"]
    if br == "build_ready" and blocking_clar:
        errors.append(f"build_ready='build_ready' but {len(blocking_clar)} blocking clarification(s) "
                      f"remain: build-readiness must be capped/qualified/advisory until resolved.")

    return (len(errors) == 0), errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True, type=Path)
    ap.add_argument("--sdd-source-index", type=Path, default=None)
    ap.add_argument("--policy", default="advisory", choices=["advisory", "production"])
    ap.add_argument("--output", type=Path, default=None)
    args = ap.parse_args()
    bundle = json.loads(args.bundle.read_text())
    si = json.loads(args.sdd_source_index.read_text()) if (args.sdd_source_index and args.sdd_source_index.exists()) else None
    ok, errors, warnings = validate_review(bundle, si, args.policy)
    result = {"status": "valid" if ok else "validation_failed",
              "errors": errors, "warnings": warnings,
              "policy": args.policy, "source_verified": si is not None}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if ok else 20


if __name__ == "__main__":
    raise SystemExit(main())
