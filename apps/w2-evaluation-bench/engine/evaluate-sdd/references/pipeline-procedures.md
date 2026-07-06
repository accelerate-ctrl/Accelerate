# Pipeline procedures (deep reference)

Per-section operating detail moved out of SKILL.md in v3.7.2 to cut always-loaded context. Read the section you are about to execute, not the whole file. Stage map: S1 reads A+B; S2 reads C+C.5; D.5 reads the checkpoint section; S4 reads E+F; S5 reads Reveal+G+report-quality.

---

## Section A: Intake (OH §3.1 row 1; OH §3.3.1; OH §3.1; OH §3.3)

Run `intake_validate.py` with the operator BRD (`--input-artefact`), the SDD input(s), `--evaluator-model`, and optionally `--methodology-version`. Mode is auto-detected from the SDD inputs:

- **Mode A, neutral intake (preferred):** `--candidate-a <sdd1> --candidate-b <sdd2> --zenagent-is a|b`. The operator supplies two position-neutral candidates and, separately, which position is the ZenAgent lane; the identity flows only into the escrow and is never echoed to stdout or `section-a-output.json`. This is what makes the blinding real isolation.
- **Mode A, legacy lane-named intake:** `--ots-sdd <ots> --zennagent-sdd <za>` (still supported; note the command line itself names the lanes, so path-level neutrality requires the neutral intake).
- **Mode B (SDD review):** `--single-sdd <sdd> [--single-sdd-origin zenagent|off_the_shelf|unspecified] [--enable-single-scoring]`. One lane; no blinding; origin is a report label only and never influences a finding.

The script performs the following steps:

1. **Structure validation** (OH §3.3 edge case 2): Validates that both SDDs are parseable, non-empty, and do not consist solely of UI artefacts (screenshots, mockups). No section convention enforced, format-agnostic principle applies. Rejects with reason if structurally unusable.

2. **Same-input hash** (OH §3.3.1): Computes SHA-256 of the input artefact. This hash proves both SDDs were scored against the same requirements. It travels with the run through all batches and surfaces in the Diagnostic Report §4.

3. **Integration detection** (OH §3.1): Counts integrations using distinct-named-systems detection, identifies named external systems, APIs, middleware, and data sources in the operator BRD. 4+ material integration points → `integration_heavy=true`, triggering the weight swap on Dim 5 (10→15) and Dim 7 (15→10) per OH §3.2. Operator may override via `--integration-count <N>` with documented justification.

4. **Provenance attestations** (OH §3.3.1; rubric §9): Records `generation_control_mode` (pipeline_generated when workflow controls generation, operator_provided when SDDs are uploaded). Stamps `same_model_structural` and `same_input_structural`, true when pipeline-generated, operator-attested when SDDs are uploaded. Records `methodology_difference_basis="ZA lane has Zennify methodology project knowledge; OTS lane does not"`.

5. **Model and methodology version** (OH §3.3.1): Records `model_version` (single value applied to both lanes and the evaluator) and `methodology_version` (the project's template/knowledge package version, defaults to `"methodology-current"` when not supplied).

6. **Lane assignment and label→file binding** (OH §3.3): Assigns the Output A / Output B labels randomly and escrows, per label, BOTH the origin AND the SDD file path (`.lane-mapping`: `{"Output A": {"origin": ..., "sdd_path": ...}, ...}`). The escrow is not opened until batch 7 reveal. Separately, a non-secret `lane_files` map (label → path, no origins) is emitted in the digest and `section-a-output.json` — this is the binding batches 3–6 use to know which SDD file to process as which lane (identity-neutral by construction under the neutral intake). `--lane-assignment fixed` remains available for deterministic ZA=A in pilot runs.

7. **Run record** (OH §3.3.1): Writes `run-record.json` with the run's provenance: run_id, run_timestamp, operator_session_id, model_version, evaluator_model_version, methodology_version, methodology_difference_basis, same_input/same_model attestations, rubric/OH/framework versions (from `contracts.FRAMEWORK_VERSION`), input_artefact_sha256, run_integration_heavy, integration_count (+ detected systems and basis), applicability_flags, placeholders for the ZMS calibration fields (filled in Section B), release-awareness paths and RR totals (filled in C.5), a `_blinding` block (origins null until batch 7 reveal), and `_outputs` paths. Lane identities are NOT stored here in any form — they live only in the `.lane-mapping` escrow (nothing is encrypted; the escrow is withheld, not encoded).

**Emit digest:** `run_id`, SHA-256, `model_version`, `methodology_version`, `run_integration_heavy`, `integration_count`, **applicability flags (13 keys)**, lane-mapping path, run-record path, operator-input paths. Discard nothing yet, all inputs are needed for subsequent batches.

**Rejection conditions** (OH §3.3): SDD is empty or unparseable; SDD consists solely of UI artefacts; operator input artefact is empty. Each triggers a halt with reason surfaced verbatim.

---

---

## Section B: ZMS calibration load (OH §3.1 row 2; OH §3.4 replacement)

Run `zms_load.py` (a thin shim in this skill's `scripts/`) which invokes the sibling ZMS skill's loader. The shim passes the applicability flags emitted by Section A and the `run_id`. The ZMS skill filters its 99-criterion register to the criteria that fire on this engagement and emits two artefacts to `/pilot-runs/<run_id>/`:

- `zms-calibration-content.json`, the engagement-filtered criteria with depth_indicator components, source labels, parent sub-criterion mapping, severity, and the path to the senior-SA reasoning playbook
- `zms-calibration-summary.json`, cover-panel-sized provenance: `zms_version`, `zms_frozen_at`, `applicable_criteria_count`, `criteria_by_source` (count by source label), `critical_floor_active`, `applicability_keys_fired`

Section D consumes the content artefact at sub-batch 4a/4b/4c/4d start; Section G consumes the summary for §4 Calibration Provenance.

**The ZMS skill is the calibration authority.** This skill's `scripts/zms_load.py` does not duplicate or re-implement ZMS, it invokes the sibling skill via subprocess. This preserves the calibration as a single source of truth (ZMS v4.6) and lets the ZMS evolve independently. A ZMS version bump cascades to the diagnostic report's §4 (the version + frozen-at travel with every run), with no change required to this skill.

**Provenance contract:** the digest carries enough for the diagnostic report to claim authority for every score. The reader of §4 sees: ZMS version, frozen-at, applicable criteria count, source distribution (e.g., *"58 from Zennify SDD standard, 41 from Well-Architected, 0 joint"* (ZMS v4.6 full register; the applicable subset varies per engagement flags)), critical-floor list, applicability keys that fired. Two runs against the same SDDs at the same ZMS version produce reproducible criteria sets; two runs across ZMS versions are comparable via the version stamp.

**Emit digest:** `zms_version`, `zms_frozen_at`, `applicable_criteria_count`, criteria-by-source distribution, critical-floor active count, `applicability_keys_fired` list, calibration-content path, calibration-summary path, sa_reasoning_playbook path. Discard the ZMS register raw content from working context, Section D reads the filtered calibration file from disk.

**Rejection conditions** (OH §3.3 edge case 1): ZMS skill not loadable; ZMS self-test exits non-zero; loader output schema invalid. Each triggers a halt with reason surfaced verbatim. Operator directed to framework operations lead (OH §5).

---

---

## Section C: Content mapping (OH §3.1 row 3; OH §2, §3.5.1, §4)

Run `content_mapping_classify.py` once per ingested SDD (two invocations, one per lane). The script receives a `components.json` produced by the model from its semantic reading of the SDD, the model finds Data Model, Security and Sharing Model, etc., whether they appear as numbered sections, capability modules, or distributed prose.

**The 8 required components** (OH §3.5): Scope and Assumptions; Data Model; Business Process Flows; Security and Sharing Model; Integration Architecture; Reporting and Analytics Design; Open Decisions Log; Confidence Annotations.

**Conditional components** (OH §3.5): Data Migration Approach; Phasing and Delivery Plan. Classified only when applicable to BRD scope. Not applicable → not counted toward the missing total.

**Classification rules** (OH §3.5.1):
- **Substantive**: The component contains meaningful design content. Default classification for borderline cases.
- **Stub**: ALL THREE conditions must be true: (1) under 200 substantive words, AND (2) fewer than 2 distinct design decisions named, AND (3) no specific Salesforce mechanism at module/class/pattern level. Borderline cases default to Substantive.
- **Missing**: The component is not present anywhere in the SDD (including as distributed content).
- **Confidence Annotations adapted criteria** (OH §3.5.1): Under 200 words across all annotations; fewer than 2 annotation entries; annotations not tied to specific SDD sections.

**Component-presence floor computation** (OH §3.5.2; rubric §6.4.1):
- 0 missing/stub over the 8 required → no floor (`null`)
- 1 or 2 missing/stub → Dim 4 capped at 10
- 3 or more missing/stub → Dim 4 capped at 7

A count of exactly 2 caps at 10, not 7. The schedule is single-sourced in `contracts.dim_4_floor_cap` (rubric §6.4.1; OH §3.5.2); never restate it from memory.

**Content mapping population** (OH §4): Populates `content-mapping.xlsx` using NLP-driven semantic extraction, not section-heading matching. The content mapping is the mechanism that handles structural variability per the format-agnostic principle (rubric §4.4; OH §2).

**Emit digest:** Per-lane `stub_missing_count_over_8_required`, per-lane `dim_4_floor_cap`, content-mapping.xlsx path, classifications summary. Discard operator SDD raw content from working context (model has the digest; SDDs remain on disk for Section D access).

---

---

## Section C.5: Release awareness research (OH §3.1 rows 3.5a, 3.5b; references/release-awareness.md)

Run the live release crosswalk once per ingested SDD, per lane (3.5a and 3.5b), via `release_crosswalk.py` (two-call live path: `extract` -> orchestrator runs `web_search` per emitted query -> `resolve`). It extracts every Salesforce mechanism named in the SDD, classifies its release status against current Salesforce-controlled sources, and emits source-cited findings that Section D consumes for Dim 3 deductions. (`release_awareness_check.py` remains as a register-only back-compat shim for the old single-call CLI; the live engine is `release_crosswalk.py`.)

**Why this runs as its own batch:** the v3.6 RR deduction schedule operated against a static `release-rules-registry-v1.json` removed in v2.0. v3.7 restores release-awareness with live, time-stamped, source-cited classification. This requires web research per mechanism, too large and too distinct from the model-driven scoring of Section D to fold into 4a/4c. Splitting it preserves the audit trail (each finding has a retrieval timestamp and source URL) and keeps Section D's working context bounded.

**Pipeline position:** between content mapping (which establishes SDD structure) and scoring (which applies the RR deduction schedule). The findings file is read by sub-batches 4a/4c.

**The script performs the following steps** (per SDD, per lane):

1. **Mechanism extraction**, NLP-driven scan of the SDD for: automation tools (Flow / Workflow / Process Builder / Apex Trigger / Approval Process / Validation Rule); security mechanisms (OWD / Sharing Rule / Permission Set / Permission Set Group / Profile / Apex Sharing); integration patterns (Platform Event / REST API / SOAP API / Bulk API / Streaming API / Change Data Capture / MuleSoft / External Services / Salesforce Connect); UI mechanisms (Lightning Web Components / Aura / Visualforce / Experience Cloud / Lightning App Builder / Dynamic Forms); data mechanisms (Big Object / Platform Cache / Custom Settings / Custom Metadata Type); AI mechanisms (Einstein / Agentforce / Prompt Builder / Model Builder); admin/dev tooling (Change Sets / DevOps Center / SFDX / Salesforce CLI).

   **Model-driven extraction (current — SDD content drives coverage):** `release_crosswalk.py extract` runs a deterministic regex **floor** that guarantees the known-legacy set is never missed, and ALSO accepts an optional `--features <file.json>` of Salesforce features the model identified while reading the SDD (`{"features": [{"name": "...", "section": "...", "quote": "..."}]}` or a bare list). Supply it so the **SDD's actual content — not the hardcoded list — determines what is verified this run**, including current features the SDD *recommends* (Data Cloud, Agentforce, Dynamic Forms, etc.). Each model-identified feature gets a currency-seeking query and is tagged `source: model_identified` in the queries file; features that coincide with the floor dedupe to a single entry (floor wins, preserving exact provenance). This is what keeps recommendations and Dim 3 grounded in the current release rather than a static catalogue. The verdict boundary is unchanged: the model sets *what to look up*, but only a Salesforce-controlled source (R23) can set a mechanism's *status*. A model-named feature with no live confirmation and no register entry resolves to `in_force_unverified` (surfaced, no deduction) — never a fabricated status. When a Salesforce source affirmatively confirms a feature is current/GA, it resolves to `in_force` (live_confirmed), which is the positive grounding signal Section D reads for Dim-3 credibility.

2. **Three-tier source query**, for each extracted mechanism, web-search Salesforce-controlled domains in priority order:
   - **Tier 1 release.salesforce.com / help.salesforce.com** for current GA / deprecation / retirement status
   - **Tier 2 help.salesforce.com tagged "retirement"** for EOL dates and superseding features
   - **Tier 3 architect.salesforce.com** for "we recommend X over Y" supersession guidance (even where Y remains supported)

   R23 enforces: every `salesforce_source` URL must resolve to a Salesforce-controlled domain. Third-party blog citations are rejected.

3. **Classification (confidence-based binary model — supersedes the older category schemes).** Each named mechanism resolves to one of the current statuses single-sourced in `contracts.py` (`RELEASE_STATUS`), and the deduction is tied to evidence strength, not retirement category:
   - `in_force` — a Salesforce-controlled source affirmatively confirms the feature is current / GA / supported. **Deduction 0.** This is the positive Dim-3 grounding signal.
   - `retired` / `end_of_support` / `superseded` — a Salesforce-controlled source confirms the feature is NOT current. These names are kept as descriptive report detail (retired = won't deploy/blocking; end_of_support = still runs but unsupported; superseded = a newer standard exists), but they all carry the SAME unified **−3** deduction. There is no longer a −5/−3 retirement-category gradation.
   - `in_force_unverified` — named in the SDD but currency not confirmed against a Salesforce source. **Deduction −1 ONLY when the live path actually ran this lane;** if the run had no web access, the mechanism is unverified for a tooling reason (not a design flaw) and deducts **0**. Never a fabricated status.

   Cumulative cap −9/lane. Authoritative values: `contracts.RR_NOT_IN_FORCE_DEDUCTION` (−3), `contracts.RR_UNVERIFIED_DEDUCTION` (−1), `contracts.RR_CUMULATIVE_CAP` (−9). Source-authority (R23) is unchanged: only a Salesforce-controlled URL can set any status; third-party evidence is corroboration only.

4. **Source anchoring**, every finding records: mechanism name, SDD section reference, verbatim ≤30-word triggering passage, classification, Salesforce source URL, retrieval timestamp, superseding feature (if applicable), EOL date (if applicable), one-sentence rationale, engagement go-live window (if EOL-relevant).

5. **Conservative defaults**, if no Salesforce-controlled source confirms a mechanism's status, it resolves to `in_force_unverified` (not a fabricated status) and is surfaced for SA review. Under the binary RR model `in_force_unverified` deducts −1 when the live path ran this lane, or 0 if the run had no web access. The script never invents classifications. R-rule R22 enforces downstream that any RR deduction in the scoring bundle traces to a finding here.

**Output schema**, written to `/pilot-runs/<run_id>/release-awareness-{A,B}.json`:

```json
{
  "run_id": "...",
  "lane": "Output A | Output B",
  "salesforce_release_at_check": "Spring '26",
  "checked_at": "2026-06-03T...",
  "extracted_mechanisms": [...],
  "findings": [
    {
      "mechanism": "Process Builder",
      "status": "end_of_support",
      "eol_date": "2025-12-31",
      "eol_passed_at_check": true,
      "recommended_successor": "Flow",
      "rr_severity": "Major",
      "rr_deduction": -3,
      "sdd_ref": "§3.2",
      "triggering_passage": "Approval routing implemented via Process Builder triggers",
      "salesforce_source": "https://help.salesforce.com/s/articleView?id=...",
      "source_retrieved_at": "2026-06-03T...",
      "rationale": "Process Builder reached End of Support December 2025; Salesforce recommends migration to Flow. Confirmed not-in-force -> unified -3.",
      "engagement_go_live_window": "post-EOL"
    }
  ],
  "summary": { "findings_total": 47,
                "by_status": { "in_force": 39, "superseded": 5, "end_of_support": 1, "retired": 1, "in_force_unverified": 1 },
                "by_confidence": { "live_confirmed": 41, "register_based": 5, "unverified": 1 },
                "rr_deductions_raw_total": -8, "rr_deductions_capped_total": -8,
                "register_stale_finding_ids": [], "recommended_successors": 7,
                "verification_coverage": "46/47 confirmed against a Salesforce-controlled source" }
}
```

**Emit digest:** Extracted mechanisms count, classifications summary, per-finding source URLs (paths only, full URLs in the file), RR deduction total, supersession recommendations total, release-awareness-{A,B}.json path. Discard web-search raw results and SDD raw content from working context.

---

---

### Section D.5: Operator Checkpoint (batch 4e)

After all four sub-batches complete and both scoring bundles are assembled, present a blinded summary to the operator before proceeding to score sheets:

- **ZMS calibration provenance**: version, frozen-at, applicable criteria count, source distribution
- Per-lane blinded headline scores (Output A total, Output B total)
- Variance flags (any dimension with stddev > 1.0)
- TRUST deductions fired (count per lane, no detail, blinding holds)
- **RR deductions fired (count per lane, sourced from release-awareness findings)**
- Content mapping summary (missing/stub counts per lane)
- **Release awareness summary** (per lane: findings total; by_status counts for in_force / in_force_unverified / superseded / end_of_support / retired; RR deduction total; recommended successors)

The operator confirms **"proceed to score sheets"** or says **"stop"** with a reason (e.g., ZMS version mismatch, content mapping missed a component, release-awareness research returned unexpected results). This checkpoint prevents wasted computation and gives the operator visibility into scoring quality before the final report is generated.

**Emit digest:** Both scoring-bundle paths, bundle assembly status, operator checkpoint result. Discard ZMS calibration content raw form from working context (paths preserved).

11. **Write scoring bundle** to `/pilot-runs/<run_id>/output-{a|b}-scoring-bundle.json` per section-d-scoring.md §2 output schema.

**Emit digest:** Both scoring-bundle paths, bundle validation status (preliminary self-check). Discard SDD raw content from working context.

---

---

## Section E: Score sheet assembly (OH §3.1 row 5; OH §3.8.1)

Run `score_sheet_populate.py` per bundle (two invocations).

**Step 1 25-rule bundle validation gate** (R1–R25 per rubric §8; OH §3.8.1): Every rule must pass. Invalid bundle → halt with failing-rule list surfaced verbatim. No skip. No fabrication. No re-run.

Key validation rules:
- R1: `blinding_label` matches requested label (Output A or Output B)
- R2: `five_runs_by_dimension` has keys 1–7, each with exactly 5 numeric scores
- R3–R5: Mean/stddev/variance flag recomputation matches bundle values
- R6: Band values ∈ {STRONG, GOOD, ADEQUATE, WEAK}
- R7: `per_dim_truth_source` schema matches the rubric §4.4 schema verbatim (with ZMS replacing benchmark in calibration_role)
- R8: `dim_3_sub_criteria` structure (4 or 5 entries depending on multi_cloud)
- R9: `dim_4_sub_criteria` consistency with CP + ADQ structure and floor_cap from Section C
- R10: Deduction format (ID matches `^(TRUST|RR)-\d+$`; value ∈ {−1, −3, −5}; the −5 tier is used by TRUST-Critical severity. RR (release) deductions under the binary RR model are only −1 (unverified, live ran) or −3 (confirmed not-in-force); RR no longer emits −5. Non-empty triggering_passage + salesforce_source required.)
- **R11 (v3.7 rewritten):** Dim 1/2/6 firewall no ZMS-as-requirements-authority phrasings. Banned patterns: *"ZMS requires/states/specifies/mandates X"*. ZMS defines the calibration depth bar; the operator BRD defines requirements.
- **R12 (v3.7 rewritten):** `zms_calibration_citations` density, non-empty on all 7 dims; each citation carries `zms_criterion_id` + `source_label` from the recognised set
- **R13 (v3.7 rewritten):** `per_dim_key_reasoning` citation linkage, references ≥ 1 zms_calibration_citation per dim
- R14: Blinding-leak scan, no ZennAgent/ZA/off-the-shelf/OTS in reasoning fields
- R15: Blinding attestation present, matching template verbatim
- **R16 (v3.7 rewritten):** Non-bias attestation present, matching template verbatim: *"I confirm that every band assignment traces to a ZMS criterion verdict cited in zms_calibration_citations; on Dim 1/2/6 every band assignment also traces to an operator-BRD passage cited in per_dim_key_reasoning; no scoring was based on prior beliefs about Salesforce architecture independent of the ZMS calibration reference."* (copy from section-d-bundle-schema.md; do not paraphrase)
- R17: Bundle well-formed JSON with all required top-level fields present (no embedded `schema_version`; the framework is one consistent v4.6 set, so R17 validates structure, not a version floor)
- R18: Operator-BRD citation on Dim 1/2/6 (story-ID pattern or BRD-section pointer)
- **R19 (NEW v3.7):** Every applicable ZMS criterion (per `zms-calibration-content.json`) appears in `content_coding.zms_components` for its parent sub-criterion. Row count equality enforced, no criterion omitted from coding.
- **R20 (NEW v3.7):** Every Partial/Absent verdict on a `Zennify SDD standard` or `Zennify + Well-Architected` criterion has an evidence anchor (verbatim ≤30-word passage) or "topic absent from SDD" marker. The in-house IP gap analysis (§6 of the report) depends on this; vacuous in-house IP claims are blocked here.
- **R21 (NEW v3.7):** Every per-dim deduction (TRUST or RR) in the bundle has a corresponding entry in either the rubric §7.1 schedule (TRUST) or `release-awareness-{A,B}.json` (RR). Cross-reference enforced, orphan deductions blocked.
- **R22 (NEW v3.7):** Every RR deduction in the scoring bundle traces to a finding in `release-awareness-{A,B}.json`. The deduction's source URL matches the finding's `salesforce_source`. R22 ensures no RR deduction without source citation.
- **R23 (NEW v3.7):** Every release-awareness finding's `salesforce_source` URL resolves to a Salesforce-controlled domain (`*.salesforce.com`, including `help.salesforce.com`, `release.salesforce.com`, `architect.salesforce.com`, `developer.salesforce.com`, `trailhead.salesforce.com`). Third-party blog citations are rejected.
- **R24 (NEW v3.7):** Every release-currency action in the diagnostic report (Section 3 actions) traces to a Release Currency Audit row (Appendix B) by mechanism name. Recommendation-to-evidence linkage enforced.

**Step 2 Derived value computation** (OH §3.9): Computes per-dimension means (rounded to 1 decimal), final scores (rounded half-up to nearest integer), enforces RR deduction cap −9 (rubric §7.2; OH §3.6.4).

**Step 3 Score sheet population** (OH §4): Populates `score-sheet-template-v4.6.xlsx` by **token replacement**. The template is authored with `{{token}}` placeholders across all six sheets (Cover, Per_Dimension_Scoring, Dim_1–7_Sub_Criteria, Deductions, Variance_Record, Narrative); the script fills every placeholder and leaves all formulas, named ranges, and merged cells intact. Formula cells (per-dimension Final `=MAX(0,D+E)`, sub-criterion mean `=AVERAGE(E:I)`, integration-heavy weight swaps reading `Cover!B18`, multi-cloud 3E activation reading `Cover!B19`, TOTAL, gate, Floor `COUNTIF`s) are never overwritten, they recompute from the filled values when the workbook is opened. The `integration_heavy` and `multi_cloud` cells are filled with the literal strings `true`/`false` so the template's `IF` formulas drive the Dim 5/7 weight swap and 3E activation automatically.

**Provenance (`--run-record` + `--zms-summary`):** invoke with `--run-record <run-record.json>` AND `--zms-summary <zms-calibration-summary.json>` so the Cover sheet's provenance block (ZMS version, ZMS frozen-at, applicable criteria count, source distribution, input SHA-256, integration count, operator session ID) is filled from the run record and ZMS summary. Scores, gates, and lift do **not** depend on these flags; without them those cover cells render blank but the rest of the sheet is complete and correct.

**Deduction convention (Dim 3):** `{{dim_N_mean}}` is the canonical per-dimension score (the 5-pass mean that `lift_calculate.py` consumes), and the Per_Dimension `Deductions applied` column is held at 0 so the per-dimension Final equals that mean, this keeps the score sheet and the lift calculation consistent and avoids double-counting. Section D therefore scores the Dim-3 five passes **net of** TRUST/RR deductions. The Deductions sheet and the Dim_3 sub-criteria block carry the full deduction audit trail (each triggered deduction's value, triggering passage, Salesforce source, and severity tier).

Invocation per lane:
```
score_sheet_populate.py --bundle output-{a,b}-scoring-bundle.json \
  --blinding-label "Output {A,B}" --run-record run-record.json \
  [--integration-heavy] \
  --template /knowledge/templates/score-sheet-template-v4.6.xlsx \
  --output /pilot-runs/<run_id>/output-{a,b}-score-sheet.xlsx
```

**Emit digest:** Per-lane final score, per-lane band per dimension (STRONG / GOOD / ADEQUATE / WEAK) and overall band, per-lane handoff inputs (Dim 7 score, overall band, variance flags), score-sheet paths. Discard scoring bundles raw content (they're on disk).

---

---

## Section F: Lift calculation (OH §3.1 row 6; OH §3.9)

Run `lift_calculate.py` against both score sheets (still A/B-labelled, blinding holds).

The script computes:

1. **Headline lift** = A − B (blinded; sign flipped at reveal to ZA − OTS).
2. **Per-dimension delta** = A[dim] − B[dim] for each dimension.
3. **Four-band quality model** per dimension and overall (rubric §6): each dimension is banded on its score as a percentage of its max, and the overall SDD is banded on its total of 100. The bands are STRONG (≥ 80: build-ready, the target standard, disposition Accept), GOOD (70–79: acceptable with the noted changes, disposition Accept-with-changes), ADEQUATE (65–69: failed, needs reworking, disposition Rework), and WEAK (< 65: should be redone, disposition Redo). The band is the verdict; there is no separate pass/fail. A variance flag on a dimension does not change its band but is reported alongside it as a confidence note.
4. **Lift interpretation band** (OH §3.9): ≥+15 Strong; +8 to +14 Moderate; +1 to +7 Marginal; 0 None; Negative → investigate.
5. **Estimation Handoff Status** per lane (OH §3.9):
   - Ready: Dim 7 band STRONG AND overall band STRONG or GOOD AND Dim 7 variance flag NOT set.
   - Conditional: Dim 7 band STRONG or GOOD AND (overall band ADEQUATE OR Dim 7 variance flag set).
   - Not Ready: Dim 7 band ADEQUATE or WEAK.
6. **Prioritised SA Review counts** per lane (OH §3.9):
   - High: dimension band ADEQUATE or WEAK OR trust deduction fired (TRUST-001 through TRUST-009).
   - Medium: variance flag on any dim OR release-awareness deduction fired.
   - Low: Confidence Annotations High-risk section identified.

**Emit digest:** Headline lift A−B, per-dim lift, gate flags, handoff status per lane, priority-review counts, lift-calc path. Discard score-sheet raw content.

---

---

## Lane reveal (between F and G) (OH §3.1 row 7; OH §3.3)

Run `lane_reveal_apply.py`. This is an explicit script call, not a narration or mental step.

The script:
1. Reads `.lane-mapping` from Section A.
2. Re-labels Output A/B → ZA/OTS using the mapping.
3. Flips lift sign to ZA − OTS (so the published number always represents ZennAgent minus off-the-shelf).
4. Recomputes underperformance flags from the ZA perspective (any dim where ZA < OTS).
5. Reads cover-panel + §4 calibration-provenance fields from `run-record.json` + `zms-calibration-summary.json` (ZMS version, frozen-at, applicable-criteria count, source distribution). `--benchmark-profile-summary` is legacy/optional and ignored under ZMS calibration.
6. Updates run record `_blinding` field to indicate reveal completed.
7. Emits `diagnostic-bundle.json` carrying all revealed values.

**After this point, lane identities are known.** All subsequent outputs use ZA/OTS labels.

---

---

## Section G: Diagnostic Report (OH §3.1 row 8; OH §4)

Run `report_build_substantive.py` (the current batch-8 default; see SKILL.md) with the diagnostic bundle and **both per-lane scoring bundles** (`--za-bundle` and `--ots-bundle`). It reuses the validated data-extraction in `diagnostic_report_populate.py` (`build_diag_tokens`) to compute every figure and the BLUF wording, then builds the report **in code** (no template) following the Pyramid Principle, BLUF, and MECE. (Mode B uses `report_build_sdd_review.py`, which renders a comprehensive SA review and shares the `report_style.py` styling toolkit; the retired `report_build_concise.py` builder has been removed.)

Structure (decision-first, three core pages then a separated appendix):
- **Section 1, Bottom line:** a BLUF callout (lift, gate decision, recommendation in three sentences), the scorecard (ZA / OTS / lift, gates, handoff), and a one-line recommendation. This is the governing thought; a reader can stop here.
- **Section 2, Where the lift comes from:** one MECE table partitioning the 100 points across the seven dimensions (Dim, max, ZA, OTS, lift, gate) with a Total row, plus a short drivers callout. This is the complete rationale.
- **Section 3, What to do:** the prioritised actions, slim (number, priority, action, where).
- **Appendix (reference only, clearly marked):** A ZMS coverage matrix, B release-currency audit (both lanes), C in-house IP gap analysis, D variance and confidence, E calibration provenance and run metadata.

The three core sections are the whole decision; everything exhaustive is demoted to the appendix so the reader is not forced through 30+ pages. R24 still ties any release-currency action to a finding reference. `diagnostic_report_populate.py` remains ONLY as the data-extraction library (`build_diag_tokens`); its legacy template-filling CLI was removed in v4.5 (provenance), and there is no diagnostic-report `.docx` template — the report is assembled in code by `report_build_substantive.py`.

```
python3 report_build_substantive.py \
  --bundle /pilot-runs/<run_id>/diagnostic-bundle.json \
  --za-bundle /pilot-runs/<run_id>/output-a-scoring-bundle.json \
  --ots-bundle /pilot-runs/<run_id>/output-b-scoring-bundle.json \
  --accuracy-gate /pilot-runs/<run_id>/accuracy-gate.json \
  --output /pilot-runs/<run_id>/diagnostic-report.docx
```

(After lane reveal, Output A may be ZennAgent or off-the-shelf depending on the run's lane mapping. The `--za-bundle` flag takes whichever lane resolved to ZennAgent — the reveal digest names it. Release-awareness files are passed to `lane_reveal_apply.py` LANE-KEYED (`--release-awareness-a/-b`, the files the crosswalk wrote); the reveal maps lane → identity internally from the escrow, so no identity knowledge is needed before it runs.)

---

### Diagnostic report quality (v3.7 transformation)

The v3.6 report had five sections, with per-dimension scoring summarised at dimension level and recommended actions framed as "strengthen Dim X" guidance. The v3.7 report carries traceability end-to-end: every score has a why; every why traces to evidence; every recommendation cites what to add, where to add it, and which authority demands it.

**Cover panel:** `run_id`, `run_timestamp`, `model_version`, `methodology_version`, **`zms_version`**, **`zms_frozen_at`**, **`applicable_criteria_count`**.

**Eight canonical sections** (OH §3.10 v3.7):

**§1, Headline Methodology Lift:** ZA − OTS lift + structural same-model attestation + lift interpretation band. *Unchanged from v3.6.*

**§1.1, Estimation Handoff Status:** Per-lane Ready / Conditional / Not Ready with derivation basis. **v3.7 enrichment:** the derivation names the specific Dim 7 ZMS criteria that drove the verdict (e.g. *"Not Ready: `7A.feature_decomposition` Absent, no work-unit decomposition; `7C.deployment_strategy` Partial, testing approach unnamed"*).

**§2, Per-Dimension Gap to Qualification:** Both lanes vs 80% threshold per dimension. **v3.7 enrichment:** below each dimension row, a per-sub-criterion mini-table shows which sub-criteria dragged the dim score down, sub-criterion ID, ZMS components fired, candidate coverage %, Present/Partial/Absent counts.

**§3, Per-Dimension Methodology Lift:** ZA − OTS per dim. **v3.7 enrichment:** lift-driver decomposition, for each non-zero per-dim lift, names the ZMS criteria where the lanes diverged (e.g., *"Dim 3 lift +4.2: ZA covered `3B.record` (Present), `3B.external_user_exposure` (Present); OTS Partial on both."*).

**§4, Calibration Provenance (rewritten from "Run Provenance"):** ZMS version, frozen-at, applicable criteria count, **source distribution table** (counts by `Zennify SDD standard` / `Well-Architected` / `Zennify + Well-Architected`), **applicability map** (which flags fired and which criteria each activated), **active critical-floor list** (the floor-applicable criteria that fired for this engagement), input SHA-256, all flags (integration_heavy, same_model_structural, same_input_structural, methodology_difference_basis), five-pass discipline note, same-model attestation. This is the audit anchor, every claim in §5/§6/§7 traces back to a row here.

**§5, ZMS Criteria Coverage Matrix (NEW):** The factually-exhaustive section. A per-dimension, per-sub-criterion table covering every applicable ZMS criterion, both lanes' verdicts, evidence anchors verbatim. Row count equality enforced (R19): `§5 row count == applicable_criteria_count`. If the reader asks "did ZA address X?", they look here.

**Release Currency Audit (Appendix B in the report):** Per-lane table covering each non-current Salesforce mechanism the live crosswalk flagged. Columns: mechanism, status (retired / end_of_support / superseded / in_force_unverified), confidence (live_confirmed / register_based / unverified), recommended successor (sourced, never invented), Salesforce source. Retired sorts first. Both lanes side-by-side so the reader sees which lane shipped retired/unsupported/superseded features.

**§6, In-house IP Gap Analysis (NEW):** Filtered view of §5 to `Zennify SDD standard` and `Zennify + Well-Architected` criteria where ZennAgent scored Partial or Absent. Auditable in-house IP gap surface, every row is a Zennify standard the ZennAgent methodology did not deliver, with the source citation that makes the gap claim defensible. Comparison with OTS shows where the gap is methodology-wide (both lanes weak) vs ZA-specific (only ZA weak, direct methodology refinement target).

**§7, Recommended Actions + Prioritised SA Review List (rewritten):** ZennAgent-only. Each action has six fields:

1. **Diagnosis**, score and threshold, the verdict on each ZMS criterion that fired short
2. **Authority**, source label per cited criterion (`Zennify SDD standard` / `Well-Architected` / `Zennify + Well-Architected`)
3. **Evidence**, the candidate SDD's actual content on this topic, verbatim quote with section reference (or "topic absent from SDD")
4. **OTS contrast** (when informative), what off-the-shelf demonstrated that ZennAgent did not, with OTS evidence quote
5. **Required content**, the components from the depth_indicator that need to be in the SDD, named concretely
6. **Where to put it**, the SDD section/component where the content belongs (from content-mapping output)

Action categories from release-awareness (unified deductions):
- **Confirmed not-in-force feature shipped** — retired / end-of-support / superseded named in the SDD and confirmed by a Salesforce source (SA Review High, **−3** unified deduction; the descriptive status still distinguishes "retired = won't deploy" from "still runs but unsupported" in the report prose).
- **Named feature, currency unverified** — named but not confirmed current; SA Review Medium, **−1** when the live path ran (0 if the run had no web access).
- **Supersession opportunity** (informational; SA Review Medium if ZA-specific, Low if both lanes).

**Design decision (preserved from v3.6):** Action surfaces are ZennAgent-only. OTS gate failures, variance, and deductions do not appear as actionable items; OTS sub-criterion coding is used as *context within* a ZennAgent action ("off-the-shelf demonstrated category X that ZennAgent did not") but never as its own row. Tables 5 (per-dim gap) and 6 (per-dim lift) remain comparative, that's the legitimate calibration purpose of the OTS data.

When ZennAgent is clean on a priority (no High / Medium / Low items for that bucket), the corresponding table shows a single positive-framed message ("ZennAgent had no gate failures or material baseline gaps on this run") rather than empty em-dash rows. Tables grow or shrink to fit the actual item count.

**§8, Variance and Confidence:** Per-dimension stddev across the five passes, variance flags, confidence-annotations risks. **v3.7 enrichment:** when a sub-criterion's ZMS coding produced inconsistent verdicts across passes, the variance is attributed to the specific criterion (the reader sees *which* judgement was uncertain, not just *that* the dim was variable).

**Coverage guarantees enforced before docx is written** (R19/R20/R24):
- Every applicable ZMS criterion appears in §5 (row count == applicable_criteria_count)
- Every Partial/Absent on a Zennify-source criterion appears in §6
- Every action (Section 3; legacy §7) cites at least one ZMS coverage-matrix row (Appendix A; legacy §5) for ZMS-driven actions OR one Release Currency Audit row (Appendix B; legacy §5.5) for release-currency actions

These checks fail the populate run if the bundle doesn't carry the evidence for an exhaustive report. No silently-thin reports.

**Emit:** Report path, run record path. Present all deliverables via `present_files`.

---

---

## Final output

After Section G completes, the orchestrator presents results in this order:

1. **Headline lift**, the methodology lift number (ZA − OTS) with the lift interpretation band and the same-model attestation.
2. **Cover panel**, run_id, model_version, methodology_version, **zms_version**, **zms_frozen_at**, **applicable_criteria_count**.
3. **Estimation Handoff Status**, per-lane Ready / Conditional / Not Ready with derivation basis (now citing specific Dim 7 ZMS criteria).
4. **Per-dimension gap and lift tables**, both lanes vs 80% threshold; ZA − OTS per dim with underperformance flags.
5. **Variance signals**, any dimension with stddev > 1.0 across the five scoring passes.
6. **In-house IP gap surface**, the Zennify-source criteria where ZennAgent scored Partial or Absent.
7. **Release currency findings**, Critical RR / RR / supersession recommendations.
8. **Prioritised SA Review List**, all High entries for ZennAgent (Critical RR, RR, ZMS gaps with deduction). Medium and Low on request.
9. **Deliverables** via `present_files`:
   - Diagnostic Report (`diagnostic-report.docx`)
   - Both score sheets (`output-za-score-sheet.xlsx`, `output-ots-score-sheet.xlsx`)
   - Content mapping (`content-mapping.xlsx`)
   - Both release-awareness files (`release-awareness-za.json`, `release-awareness-ots.json`)
   - ZMS calibration content (`zms-calibration-content.json`)
   - Run record (`run-record.json`)
   - Revealed lane mapping

---
