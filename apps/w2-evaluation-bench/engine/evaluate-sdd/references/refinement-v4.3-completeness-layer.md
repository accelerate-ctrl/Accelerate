# Zennify Solutioning Evaluation Framework — Completeness & Adaptability Refinement Package

> **ARCHIVAL.** This document describes the v4.3 completeness layer. Its module (`scripts/_completeness_layer.py`), the `registries/` tree, and the associated schemas are **not invoked by the v4.6 batch pipeline** (SKILL.md, the system prompt, and pipeline-procedures.md never call them). Retained for lineage only.

Status: v4.2 → v4.3 (additive). Existing 447-assertion suite stays green throughout. This package documents what was built, what was deliberately built differently from the source design, what is deferred, and the honest caps that prevent overclaiming.

## 1. Executive summary

The framework's spine (dual-mode, ZMS calibration, release crosswalk, blinding, R1–R25, per-phase gates, branded report) is sound. Its real weakness was that it could not distinguish "assessed and weak" from "could not reliably assess." This refinement adds a **Completeness & Adaptability Layer** that makes the system know what it can judge, detect what context is missing, abstain when out-of-distribution, and resolve platform facts live rather than from stale stores.

One architectural decision overrides the source design: the operator confirmed there is **no human owner** for registries and that domain/feasibility knowledge "should shift with the Salesforce docs and releases." Therefore feasibility/licensing/currency **facts are resolved LIVE** through the existing Salesforce-source path (Docs MCP when connected, `*.salesforce.com`-scoped search under the R23 guard) and the operator-supplied org-context pack. Registries hold only **detection signals, taxonomy, and routing logic** — content that does not go stale on a Salesforce release. This is the only honest way to build the design with no maintainer; a hand-keyed license matrix would assert false feasibility the moment a release shipped.

## 2. New files

Scripts: `source_index_build.py`, `evidence_anchor_verify.py`, `_completeness_layer.py` (consolidates domain detection, OOD, org-context, feasibility, clarification, completeness — kept in one module to limit surface area; each function independently testable).

Schemas (`schemas/`): source-index, evidence-verification, requirements-trace, clarification-queue, org-context, domain-profile, ood-result, feasibility-result, completeness-profile.

Registries (`registries/`): `domain_profiles/` (9 profiles + manifest, detection-signals only), `feasibility/feasibility_logic.json` (taxonomy + checks, NO fact matrix), `ood/ood_thresholds.json`, `clarification/ambiguity_patterns.json`, `policy_profiles/` (dev, advisory, production, strict).

Data: `data/gold-corpus/` container (cases/splits/coverage) — structure only; see cap in §7.

## 3. Modified files (planned integration; foundation built first)

`score_sheet_populate.py` — R25 extended to R25a–R25e (R25a heuristic groundedness already live; R25b exact-source-match, R25c negative-evidence, R25e relevance now available via `evidence_anchor_verify`). `pipeline_integrity.py` — add S1-setup gates for completeness artifacts. `report_build_substantive.py` / `report_build_sdd_review.py` — add reliability-basis, review-completeness-level, OOD-status, feasibility, clarification sections. SKILL.md / system prompt — document the layer and the live-fact principle.

## 4. Script-by-script behavior (built)

`source_index_build.py`: deterministically parses BRD/SDD (.md/.txt/.docx) into hashed, addressable segments with char offsets and word counts. Enables exact quote matching and source-derived word counts. Same input → same index.

`evidence_anchor_verify.py`: separates `quote_exists` (deterministic, against the index — R25b) from `quote_supports_verdict` (relevance via depth-component coverage — R25e). Absent findings require `negative_evidence` (R25c). Statuses: verified / verified_weak / verified_absent / fabricated_or_unmatched / irrelevant_quote / unverified_absent. **A fabricated quote and a real-but-irrelevant quote both fail** — verified end-to-end.

`_completeness_layer.py`: `detect_domains` (signal match → confidence), `detect_ood` (in/near/out/not_assessable; weak≠OOD), `validate_org_context` (absent→feasibility-not-confirmed), `assess_feasibility` (taxonomy; facts from org-context + live path), `build_clarifications` (blocking/high/medium/low), `build_completeness` (C0–C5; **C5 unreachable without human labels**).

## 5. Validation rules added

R25b exact/normalized source match; R25c negative-evidence for Absent; R25e relevance (irrelevant quote rejected); OOD abstention; org-context gating of feasibility claims; clarification-blocking caps build-readiness.

## 6. Honest caps enforced in code (not just prose)

- **C5 "production-complete" is unreachable.** `build_completeness` cannot emit C5; max is C4 micro-calibrated. C5 requires human-validated benchmark labels the system does not have.
- **Four-SDD corpus ≠ generalization.** Reliability label capped at MICRO-CALIBRATED; leave-one-out on n=4 is built as mechanics but not reported as accuracy-with-CI.
- **Release-current ≠ licensed/feasible.** `assess_feasibility` returns SA_CONFIRMATION_REQUIRED / LICENSE_UNKNOWN, never CONFIRMED_FEASIBLE, when org context is absent.
- **Weak ≠ OOD.** Tested explicitly: a covered in-domain SDD stays in_distribution regardless of quality.
- **No stale fact stores.** Registries hold logic; facts resolve live under R23.

## 7. Risks & tradeoffs

OOD detection has false-positive/negative risk → default advisory, always explain why, never bare "cannot assess." Live fact resolution depends on the Salesforce-source path being reachable → graceful degradation to unverified when not. Single consolidated layer module trades some modularity for far less surface area on a system that must stay green. The completeness layer adds setup-phase artifacts → pipeline integration must gate them without blocking simple runs.

## 8. Migration from v4.2

Additive: no bundle-structure change required for existing artifacts. New artifacts are optional inputs to scoring/report; absence degrades gracefully (the completeness profile simply reports lower coverage). Run provenance should record the new registry versions. Existing runs remain interpretable.

## 9. Contradictions/drift corrected

The source design specified hand-maintained license/feasibility matrices with human owners and review_by dates. With no owner and a "track the docs" mandate, that is replaced by live resolution + logic-only registries. This is a deliberate, documented deviation that makes the design *safe* to run unmaintained — honoring the source document's own warning that a stale matrix is worse than none.

## 10. What remains for full statistical/external validity

Unchanged from prior honest assessment and not solvable by code: human-validated, dual-labeled, stratified criterion verdicts (~270+ across all verdict classes), inter-rater agreement (κ), train/test split, and decorrelated scoring passes. This refinement makes the system *ready* to consume those and *honest* about lacking them; it does not manufacture them.
