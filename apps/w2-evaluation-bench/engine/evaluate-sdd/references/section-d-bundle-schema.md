# Section D bundle schema and validation rules (read at bundle assembly: end of 4b / 4d)

## 2. Output bundle schema (Section D → Section E)

Write to `/pilot-runs/<run_id>/output-{a|b}-scoring-bundle.json`:

> **R8c (score-sheet auditability):** every applicable sub-criterion across all seven dimensions must carry a five-element numeric `scores` array (the five passes). This is enforced by the validator so the `Dim_1-7_Sub_Criteria` sheet is always fully populated. `3E` (multi_cloud_architecture) is required only on multi-cloud engagements.

**`content_coding` (every scored sub-criterion).** Each sub-criterion across all seven dimensions carries a `content_coding` block recording the candidate's verdict per ZMS criterion that maps to this sub-criterion. The `zms_components` array lists the ZMS criteria fired (from `zms-calibration-content.json` → `criteria_by_dim_and_sub`); each entry carries verdict (Present/Partial/Absent/NA), source label, per-depth_indicator-component results, and the verbatim evidence anchor. Coverage is computed from the verdict distribution. The coding is the auditable basis for the sub-criterion score and feeds `zms_calibration_citations` observations. Score-sheet population (Section E) consumes the existing `scores`/`reasoning` fields; `content_coding` is the evidence trail and is preserved in the bundle for audit and downstream consumption by the diagnostic report's §5 ZMS Coverage Matrix and §6 In-house IP Gap Analysis.

```json
{
  "run_id": "...",
  "blinding_label": "Output A",
  "header": {
    "zms_version": "4.6",
    "zms_frozen_at": "2026-06-03T...",
    "evaluator_model": "<resolved from session context>",
    "model_version": "<single value applied to both lanes>",
    "methodology_version": "<project template/knowledge package version>"
  },
  "five_runs_by_dimension": {
    "1": [0,0,0,0,0], "2": [0,0,0,0,0], "3": [0,0,0,0,0],
    "4": [0,0,0,0,0], "5": [0,0,0,0,0], "6": [0,0,0,0,0], "7": [0,0,0,0,0]
  },
  "dim_1_sub_criteria": {
    "requirement_parsing_depth":          {"scores": [0,0,0,0,0], "max": 5, "reasoning": "...",
      "content_coding": {
        "zms_components": [
          {"zms_criterion_id": "1A.object", "source_label": "Zennify SDD standard", "severity": "High",
           "verdict": "Present", "evidence_anchor": "Complaint__c with CFPB taxonomy fields, sdd_ref: §2 Data Model",
           "components_present": ["named Salesforce object (standard or custom)", "API name provided for custom objects"],
           "components_partial": [], "components_absent": []},
          {"zms_criterion_id": "1A.field", "source_label": "Zennify SDD standard", "severity": "High",
           "verdict": "Partial", "evidence_anchor": "Fields named but purpose unstated, sdd_ref: §2 Data Model",
           "components_present": ["field extension named"],
           "components_partial": ["field type specified"],
           "components_absent": ["stated purpose for each field"]}
        ],
        "candidate_present": ["named Salesforce object (standard or custom)"],
        "candidate_partial": ["field type specified"],
        "candidate_absent": ["stated purpose for each field"],
        "coverage": 0.75
      }},
    "stakeholder_persona_recognition":    {"scores": [0,0,0,0,0], "max": 5, "reasoning": "...", "content_coding": { }},
    "constraint_assumption_extraction":   {"scores": [0,0,0,0,0], "max": 5, "reasoning": "...", "content_coding": { }}
  },
  "dim_2_sub_criteria": {
    "functional_requirement_traceability": {"scores": [0,0,0,0,0], "max": 5, "reasoning": "..."},
    "nfr_coverage":                        {"scores": [0,0,0,0,0], "max": 5, "reasoning": "..."},
    "gap_risk_identification":             {"scores": [0,0,0,0,0], "max": 5, "reasoning": "..."}
  },
  "dim_3_sub_criteria": {
    "cloud_module_selection":     {"scores": [0,0,0,0,0], "max": 5, "reasoning": "..."},
    "trusted_design":             {"scores": [0,0,0,0,0], "max": 5, "reasoning": "..."},
    "easy_design":                {"scores": [0,0,0,0,0], "max": 5, "reasoning": "..."},
    "adaptable_design":           {"scores": [0,0,0,0,0], "max": 5, "reasoning": "..."},
    "multi_cloud_architecture":   null
  },
  "dim_4_sub_criteria": {
    "component_presence":             {"scores": [0,0,0,0,0], "max": 9, "reasoning": "..."},
    "architectural_decision_quality": {"scores": [0,0,0,0,0], "max": 6, "reasoning": "..."},
    "floor_cap": null,
    "raw_sum_before_floor": 0,
    "final_dim_4_score": 0
  },
  "dim_5_sub_criteria": {
    "dependency_id_classification":    {"scores": [0,0,0,0,0], "max": 4, "reasoning": "..."},
    "assumption_documentation":        {"scores": [0,0,0,0,0], "max": 3, "reasoning": "..."},
    "integration_failure_modes":       {"scores": [0,0,0,0,0], "max": 3, "reasoning": "..."}
  },
  "dim_6_sub_criteria": {
    "in_out_delineation":     {"scores": [0,0,0,0,0], "max": 4, "reasoning": "..."},
    "phasing_prioritisation": {"scores": [0,0,0,0,0], "max": 3, "reasoning": "..."},
    "scope_creep_resistance": {"scores": [0,0,0,0,0], "max": 3, "reasoning": "..."}
  },
  "dim_7_sub_criteria": {
    "estimable_work_units":       {"scores": [0,0,0,0,0], "max": 5, "reasoning": "..."},
    "complexity_effort_indicators": {"scores": [0,0,0,0,0], "max": 5, "reasoning": "..."},
    "delivery_readiness_signals":  {"scores": [0,0,0,0,0], "max": 5, "reasoning": "..."}
  },
  "deductions": [
    {
      "id": "TRUST-001",
      "source": "Trust schedule (OH §3.6.4)",
      "trust_schedule_ref": "TRUST-001",
      "deduction": -3,
      "triggering_passage": "<SDD section ref + verbatim quote ≤30 words>",
      "salesforce_source": "<architect guide URL>",
      "rationale": "<one sentence>"
    },
    {
      "id": "RR-001",
      "source": "Release-awareness finding (release-awareness-{a|b}.json)",
      "release_finding_ref": "RR-A-001  (a finding_id from release-awareness-{a|b}.json, copied into this bundle's release_awareness_findings — R22 cross-checks this exact value)",
      "deduction": -3,
      "triggering_passage": "<SDD section ref + verbatim quote ≤30 words>",
      "salesforce_source": "<help.salesforce.com URL with retrieval timestamp>",
      "rr_severity": "Major",
      "rationale": "<one sentence>"
    }
  ],
  "per_dim_band":          {"1": "STRONG", "2": "STRONG", "3": "STRONG", "4": "STRONG", "5": "STRONG", "6": "STRONG", "7": "STRONG"},
  "per_dim_mean":          {"1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0, "5": 0.0, "6": 0.0, "7": 0.0},
  "per_dim_stddev":        {"1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0, "5": 0.0, "6": 0.0, "7": 0.0},
  "per_dim_variance_flag": {"1": false, "2": false, "3": false, "4": false, "5": false, "6": false, "7": false},
  "per_dim_truth_source": {
    "1": "Operator BRD (requirements truth) + ZMS calibration reference",
    "2": "Operator BRD (requirements truth) + ZMS calibration reference",
    "3": "Operator BRD (requirements truth) + Salesforce platform standards (technical truth) + ZMS calibration reference",
    "4": "Operator BRD (requirements truth) + Content Mapping (structural truth) + ZMS calibration reference",
    "5": "Operator BRD (requirements truth) + ZMS calibration reference",
    "6": "Operator BRD (requirements truth) + ZMS calibration reference",
    "7": "Operator BRD (requirements truth) + ZMS calibration reference"
  },
  "per_dim_key_reasoning": {"1": "...", "2": "...", "3": "...", "4": "...", "5": "...", "6": "...", "7": "..."},
  "narrative_per_dim":     {"1": "...", "2": "...", "3": "...", "4": "...", "5": "...", "6": "...", "7": "..."},
  "zms_calibration_citations": {
    "1": [{"zms_criterion_id": "1A.object", "source_label": "Zennify SDD standard",
           "brd_ref": "<operator story ID>", "sdd_ref": "§2 Data Model",
           "verdict": "Present", "evidence_anchor": "≤30 words verbatim",
           "observation": "<calibration observation, ≥30 chars>"}],
    "2": [], "3": [], "4": [], "5": [], "6": [], "7": []
  },
  "zms_calibration": {
    "applicable_criteria": ["<copied from zms-calibration-content.json applicable_criteria — id objects or the slice for this sub-batch group; merged across 4a+4b (or 4c+4d) at bundle assembly. R19 checks every id here appears in content_coding.>"]
  },
  "content_coding": {
    "<sub_criterion_key>": {
      "zms_components": [
        {"zms_criterion_id": "1A.object", "source_label": "Zennify SDD standard", "severity": "High",
         "verdict": "Present", "evidence_anchor": "Complaint__c with CFPB taxonomy fields, sdd_ref: §2 Data Model",
         "components_present": ["named Salesforce object (standard or custom)"],
         "components_partial": [], "components_absent": []}
      ],
      "candidate_present": ["<category names coded Present — consumed by the report's gap analysis>"],
      "candidate_partial": [],
      "candidate_absent": [],
      "coverage": 0.75
    }
  },
  "release_awareness_findings": [
    {"finding_id": "RR-A-001", "mechanism_name": "...", "status": "...", "salesforce_source": "https://help.salesforce.com/..."}
  ],
  "confidence_annotations_high_risk": false,
  "blinding_attestation":  "I confirm that this scoring bundle was produced without knowledge of which lane (ZennAgent or off-the-shelf) this SDD represents. All references use the blinding label assigned at intake.",
  "non_bias_attestation":  "I confirm that every band assignment traces to a ZMS criterion verdict cited in zms_calibration_citations; on Dim 1/2/6 every band assignment also traces to an operator-BRD passage cited in per_dim_key_reasoning; no scoring was based on prior beliefs about Salesforce architecture independent of the ZMS calibration reference."
}
```

Both attestations are enforced character-for-character (R15, R16). `content_coding` is a REQUIRED TOP-LEVEL field (R17) keyed by sub-criterion key; each sub-block's `zms_components` entries use the flat keys `zms_criterion_id` / `source_label` / `verdict` / `evidence_anchor` (R19, R20 read exactly these). A per-sub mirror inside `dim_N_sub_criteria.<sub>.content_coding` is permitted for readability, but the top-level map is what validation and the report consume. `zms_calibration.applicable_criteria` (copied from the loader output) is what arms R19; omitting it silently disables the exhaustiveness check. `release_awareness_findings` (copied from this lane's `release-awareness-{a|b}.json`) is what arms R21/R22 finding-id cross-checks.

## 3. Bundle validation rules (Section E enforces; 25 rules, v4.6)

Run `score_sheet_populate.py --validate-bundle-only` to enforce. Run halts on any failure; surface the specific check verbatim to the operator. The 25 checks (R1–R18 carried from v3.0 with R11/R12/R13/R16 rewritten for ZMS; R19–R24 added v3.7; R25 added v4.2):

1. `blinding_label` matches the requested label
2. `five_runs_by_dimension` has keys `{1..7}`, each a list of 5 numerics
3. `per_dim_mean[k]` ≈ `round(mean(scores), 1)` for each k
4. `per_dim_stddev[k]` ≈ `round(stdev(scores), 2)` for each k
5. `per_dim_variance_flag[k]` matches `stddev > 1.0`
6. `per_dim_band` keys 1..7, each in `{STRONG, GOOD, ADEQUATE, WEAK}`
7. `per_dim_truth_source` matches the §2 schema verbatim (ZMS-aware version)
8. `dim_3_sub_criteria` has 4 entries (5 if multi_cloud per rubric §5); scores in bounds; reasoning ≥50 chars each
9. `dim_4_sub_criteria` consistent; `floor_cap` matches input bundle
10. Each deduction: `id` matches `^(TRUST|RR)-\d+$`; `deduction` ∈ {−1, −3, −5} (the −5 tier is TRUST-Critical only; RR/release deductions under the binary RR model are −1 for `in_force_unverified` when the live path ran, or −3 for any confirmed-not-in-force status, and never −5); non-empty `triggering_passage` and `salesforce_source`
11. **Dim 1/2/6 firewall (v3.7 rewritten)**: `per_dim_key_reasoning[1,2,6]` and `zms_calibration_citations[1,2,6][*].observation` do not contain ZMS-as-requirements-authority phrasings. Permits calibration phrasings.
12. **ZMS-citation check (v3.7 rewritten, all 7 dims)**: `zms_calibration_citations[1..7]` is non-empty; each entry carries, at the entry's TOP LEVEL: `zms_criterion_id` (form `^\d[A-Z]\.[a-z_]+$`), `source_label` from the recognised set, `verdict` ∈ {Present, Partial, Absent, NA}, and `evidence_anchor` (Present requires a substantive ≥20-char anchor; enforced as the Present half of R20). `brd_ref`, `sdd_ref`, and `observation` (≥30 chars) accompany the entry but are not nested under a `candidate` object.
13. **Non-bias citation density (v3.7 rewritten, all 7 dims)**: `per_dim_key_reasoning[1..7]` references at least one `zms_calibration_citations` entry for that dimension (≥2 distinctive content-words overlap).
14. **Blinding-leak scan (widened)**: no occurrence of `ZenAgent | ZennAgent | ZA | off-the-shelf | OTS` anywhere in `per_dim_key_reasoning`, `narrative_per_dim`, `dim_3_sub_criteria[*].reasoning`, or `dim_4_sub_criteria[*].reasoning`.
15. `blinding_attestation` present and matches the verbatim template
16. `non_bias_attestation` present and matches the v3.7 verbatim template (cites ZMS, not benchmark)
17. Bundle is well-formed JSON; all required top-level fields present (no embedded `schema_version` — the system is one consistent v4.5 set)
18. **Operator-BRD citation on Dim 1/2/6 (new)**: `per_dim_key_reasoning[1,2,6]` each contains at least one operator-BRD reference. Default patterns: story-ID conventions (`SF-\d+`, `US-\d+`, `STORY-\d+`, `AC-?\d+`) OR a BRD-section pointer (`BRD §\d`, `section \d`, `requirement \d`). Configurable to match the operator's actual ID conventions.
19. **ZMS coverage exhaustiveness (v3.7)**: every applicable ZMS criterion (from `zms-calibration-content.json` → `applicable_criteria`) appears in at least one sub-criterion's `content_coding.zms_components` array, with the parent sub-criterion determined by `zms-22-mapping.json`. No applicable criterion is silently dropped from the scoring trail.
20. **Evidence-anchor discipline on Partial/Absent Zennify-source criteria (v3.7)**: every `zms_components[]` entry with `verdict ∈ {Partial, Absent}` and `source_label ∈ {"Zennify SDD standard", "Zennify + Well-Architected"}` carries an `evidence_anchor` documenting what was searched for (the depth_indicator components attempted) and the SDD sections inspected. This is the audit trail that powers §6 In-house IP Gap Analysis.
21. **Deduction → schedule cross-reference (v3.7)**: every entry in `deductions[]` whose `id` matches `^TRUST-\d+$` carries a `trust_schedule_ref` naming one of the TRUST schedule entries (TRUST-001..009 per OH §3.6.4 + refinement P2-C). Every entry whose `id` matches `^RR-\d+$` carries a `release_finding_ref` naming a `finding_id` present in the bundle's `release_awareness_findings` (copied from `release-awareness-{a|b}.json`).
22. **RR deduction traces to release-awareness finding (v3.7)**: each `RR-*` deduction's `release_finding_ref` matches a `finding_id` in the bundle's `release_awareness_findings` for the same lane (finding IDs are `RR-{A|B}-NNN`).
23. **Salesforce-controlled source URL only (v3.7)**: every `salesforce_source` on a `RR-*` deduction is a URL on a domain in the Salesforce-controlled whitelist (`help.salesforce.com`, `architect.salesforce.com`, `developer.salesforce.com`, `releasenotes.docs.salesforce.com`, `trailhead.salesforce.com`, `salesforce.com`). Third-party blogs and forums are rejected as primary source, R23 is the gate.
24. **Release action ↔ audit row (v3.7)**: every `RR-*` deduction surfaces as a Release Currency Audit row in the diagnostic report (Appendix B); the row is consistent with the deduction's `release_finding_ref` and severity (Critical/Major/Minor per R22).
25. **Evidence-anchor groundedness (R25)**: every `zms_calibration_citations[*].evidence_anchor` must be a genuine SDD quote, not a restatement of the verdict (`coded Partial`, `verdict: Absent`, `scored Present`), a deferral (`see capability detail`, `refer to …`, `as noted above`), or a placeholder (`TBD`, `not specified`, `N/A`). Verdict-restatements are rejected for ANY verdict; deferrals/placeholders are rejected for `Present`/`Partial` (asserted coverage must quote what the SDD actually said), and `Present`/`Partial` anchors must carry ≥4 words of real content. This is the grounding gate: it stops ungrounded, robotic gap cards from reaching the report by forcing every verdict to cite the SDD's actual words.

### R11 (narrowed): banned phrasings on Dim 1/2/6

Phrasings that treat ZMS as factual authority on what the operator BRD requires:

- *"the ZMS (criterion|standard|calibration) (states|says|specifies|requires|covers) (requirement|that|the)..."*
- *"per ZMS, (the requirement|the BRD|story|AC) is..."*
- *"according to ZMS, (requirement|story|AC) X is..."*
- *"compared to the ZMS bar, (this is missing|the candidate is missing) (requirement|story|AC)..."*
- *"the ZMS criterion's requirement / story / AC..."*

ZMS is the **calibration authority** (the bar the candidate should reach), never the **requirements authority** (what the operator BRD asks for). On Dim 1/2/6 specifically, the requirements truth source is exclusively the operator BRD; ZMS calibrates the depth at which BRD requirements are addressed but does not extend or rewrite them.

### R11: allowed phrasings on Dim 1/2/6 (calibration use)

- *"ZMS criterion `1A.field` (Zennify SDD standard) requires field-extension naming with type and stated purpose; the candidate addresses operator story `SF-12` with named fields but unstated purposes, placing it Partial on this criterion."*
- *"ZMS calibration for Scope Discipline (`6A.scope_boundary_table`, Zennify SDD standard) requires explicit in-scope / out-of-scope tables tied to story IDs. The candidate's scope on operator stories `US-3` through `US-7` is stated narratively without per-story binding."*
- *"Operator story `SF-42` requires field-level audit. ZMS criterion `3B.field` (Well-Architected, Trusted) calibrates the depth at which FLS should be addressed (via permission set, not profile). The candidate's coverage uses profile-only FLS, one tier below the calibration bar."*

## Executive narrative (diagnostic bundle, Mode A)

The diagnostic bundle (lane_reveal_apply.py output) may carry an `exec_narrative` object consumed by `report_build_substantive.py` to render the Executive Summary at full (reference-report) depth. Keys, each a grounded paragraph naming the run's actual dimensions/scores/mechanisms: `what_we_evaluated`, `the_verdict`, `where_paid_off`, `where_trailed`, `release_currency`, `confidence_caveats`, `what_next`. The model authors it at S5 and passes it via `lane_reveal_apply.py --exec-narrative`. Absent keys are omitted (no filler); a fully absent object yields the thin generated BLUF only — which is the most common cause of a shallow report, so author the full set every Mode A run.

### R10 (v4.3): type-aware deductions
RR-* (release-currency) deductions are validated as only **-1 or -3 — never -5**; -5 is reserved for TRUST-* critical issues. A `salesforce_source` is required on RR-* deductions only (not TRUST-*).

### R25 (v4.3): source-verified evidence grounding
When `score_sheet_populate.py` is given `--sdd-source-index`, R25 escalates from heuristic groundedness to **provable source verification**: R25b (the anchor must resolve in the SDD source index — fabricated/mis-transcribed quotes fail), R25c (Absent verdicts must carry `negative_evidence`), and R25e (Present/Partial anchors must *support* the verdict, not merely exist — real-but-irrelevant quotes fail). Without the index, R25 falls back to the heuristic check (back-compatible).
