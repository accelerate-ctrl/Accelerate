# Section D core: scoring discipline (read in EVERY scoring sub-batch)

*Scoring procedure, aligned to evaluate-sdd v4.6, rubric v4.6, operations handbook v4.6, and ZMS calibration skill v4.6 (frozen, 99 criteria). Uses the ZMS calibration model. Mode A only — Mode B uses the qualitative SA review, not this scoring procedure.*

Read this **at Section D**, before scoring either ingested SDD. Read it again before scoring the second SDD. Also re-read the **SA reasoning playbook** (loaded by ZMS at Section B; path in `zms-calibration-content.json`) fresh at every sub-batch, the playbook is what teaches the evaluator how to apply ZMS components to specific SDD content. The discipline is deterministic; the variance comes from the five-pass uncertainty discipline, not from re-reading.

## The ZMS calibration model recap

The Zennify Methodology Spec (ZMS) is a frozen, versioned calibration reference loaded once per run by `zms_load.py` in Section B. The output is `zms-calibration-content.json`, the 99 ZMS criteria filtered to those that fire on this engagement per the applicability flags. Each criterion carries: ID, name, parent sub-criterion (one of the rubric's 22), depth_indicator, decomposed `depth_indicator_components` (1–6 specific things to search for in the SDD), source label (`Zennify SDD standard` / `Well-Architected` / `Zennify + Well-Architected`), severity, and applicability.

Scoring asks: for each ZMS criterion that fires, does the candidate SDD contain the substantive content the depth_indicator describes? The candidate is coded against the ZMS components, not against a paired exemplar from a Library. The model is engagement-aware via applicability flags; engagement-independent in calibration depth.

The ZMS plays a role across all 7 dimensions as the SA-grade quality calibration reference, it codifies what production-quality reasoning looks like at the criterion level, drawn from the Zennify SDD standard and the Salesforce Well-Architected Framework. The **operator BRD is always the requirements truth source**, ZMS never introduces requirements absent from the operator BRD. What differs by dimension is the **technical truth source** and the **ZMS role**:

- **Dim 1, 2, 6**: operator BRD is the requirements truth source. ZMS is consulted only as a quality calibration depth bar (what SA-grade comprehension / coverage / scope discipline looks like). The operator BRD is not substituted by ZMS; reasoning on these dims must cite operator BRD passages for the requirements basis.
- **Dim 3, 4, 5, 7**: operator BRD remains the requirements truth source. Where Salesforce platform correctness matters (Dim 3 especially), current Salesforce documentation and **release-awareness findings from Section C.5** are the technical authority. ZMS calibrates expected depth (what SA-grade design looks like) but does not introduce requirements absent from the operator BRD.

Story IDs in the operator BRD (e.g. `SF-336`) and ADR IDs in the candidate SDD (e.g. `ADR-801`) are natural anchors. Acceptance Criteria within each story (AC1, AC2…) are the granular requirement points.

**Acceptance-criterion IDs as requirement anchors.** Not every BRD uses `SF-N` / `US-N` story IDs. Some BRDs express requirements as narrative user stories (*"As a … I need … so that …"*) whose granular, traceable units are the acceptance criteria (`AC1`, `AC2`, … or story-scoped forms such as `S3-AC2`). In these BRDs the **acceptance criterion is the requirement ID**: it is the unit that traces from BRD to SDD and the citation anchor used in `zms_calibration_citations` and `per_dim_key_reasoning`. AC identifiers, story headers (`As a <role>`), and BRD section references are all admissible operator-BRD references for R18, the requirement is that reasoning is anchored to a locatable BRD unit.

## Source-label transparency (replacing per-dim benchmark quality annotations)

The v3.0 procedure used `per_dim_quality` annotations to vary the calibration bar by dimension. ZMS removes this concept, the calibration bar is **frozen** at the ZMS version and constant across runs. Instead, the **source label** per criterion provides authority transparency:

- `Zennify SDD standard`, the criterion measures Zennify in-house IP. Gaps here surface in §6 of the diagnostic report (In-house IP Gap Analysis).
- `Well-Architected`, the criterion measures Salesforce Well-Architected guidance (Trusted / Easy / Adaptable).
- `Zennify + Well-Architected`, reserved joint label for a criterion required identically by both authorities. **In ZMS v4.6 this label is unused** (the B1 re-attribution resolved every former joint criterion to a single authority); it remains defined for forward compatibility.

The diagnostic report cites the source label per criterion. A reader reviewing a gap on `3B.record` (Well-Architected) sees the authority that requires the depth, and for a `Zennify SDD standard` gap such as `4A.reporting_analytics`, the in-house IP claim is anchored to Zennify's own standard, not asserted.

**How to use source labels in scoring:**
1. Score the candidate against the criterion's `depth_indicator_components` per the SA reasoning playbook's decision protocol.
2. The source label does not affect the verdict, it travels into the scoring bundle so the diagnostic report can cite authority correctly.
3. Critical-floor criteria (severity Critical) cap the parent sub-criterion at the Good band boundary when scored Absent on an applicable engagement, regardless of source label: a wholly missing critical component prevents a Strong score but does not by itself condemn an otherwise sound design.

## Two citation flavours

Every dimension produces `zms_calibration_citations[<dim>]` entries. The structure is the same; the semantic differs by dimension family:

**On Dim 3/4/5/7 calibration with technical truth.** The citation documents the candidate's coverage of the ZMS depth_indicator components. The ZMS side records the criterion ID, source label, and components required; the candidate side records verdicts (Present/Partial/Absent) per component with verbatim ≤30-word evidence anchors. On Dim 3, release-awareness findings supplement as the freshness check.

**On Dim 1/2/6 calibration-only.** The citation documents the candidate's reasoning depth on parallel operator-BRD content. The ZMS side records the criterion and depth_indicator components; the candidate side records the candidate's reasoning level. The ZMS is NOT cited as authority on what the operator BRD requires, only on what the quality bar looks like.

Bundle validation rule R11 rejects ZMS-as-requirements-authority phrasings on Dim 1/2/6. Bundle validation rule R18 requires Dim 1/2/6 reasoning to cite at least one operator-BRD passage (story-ID pattern or BRD section reference).

## Non-bias attestation

Every band assignment must trace to a ZMS criterion component cited in `zms_calibration_citations` (calibration reference for all dims) AND, on Dim 1/2/6, also to an operator-BRD passage cited in `per_dim_key_reasoning`. On Dim 3/4/5/7, the operator BRD remains the requirements truth source, with Salesforce platform standards + release-awareness findings as the technical authority. Prior beliefs about Salesforce architecture independent of ZMS are inadmissible.

The rubric's mechanical rules (band thresholds, 80% gate, deduction values, floor cap, integration-heavy weight swap, multi-cloud applicability) are the only place rule application is admissible without ZMS grounding, the rubric is itself an SA-derived artefact maintained alongside ZMS.

Sign the `non_bias_attestation` field verbatim:

> *"I confirm that every band assignment traces to a ZMS criterion verdict cited in zms_calibration_citations; on Dim 1/2/6 every band assignment also traces to an operator-BRD passage cited in per_dim_key_reasoning; no scoring was based on prior beliefs about Salesforce architecture independent of the ZMS calibration reference."*

(This wording is enforced character-for-character by R16 in `score_sheet_populate.py`. Do not paraphrase, re-punctuate, or substitute "depth_indicator component" for "criterion verdict".)
## 1. Input bundle (Section C → Section D)

Available at Section D time. The model assembles this from `section-a-output.json` + `zms-calibration-content.json` + `section-c-output-{a,b}.json` + `release-awareness-{a|b}.json` before scoring begins:

```json
{
  "run_id": "W2-YYYY-MM-DD-xxxxxxxx",
  "blinding_label": "Output A | Output B",
  "model_version": "<resolved from session context>",
  "methodology_version": "<resolved from project state>",
  "sdd": {"path": "...", "content_format": "docx|md|txt"},
  "operator_input": {"path": "...", "content_format": "..."},
  "zms_calibration": {
    "zms_version": "4.6",
    "zms_frozen_at": "2026-06-03T...",
    "applicable_criteria_count": 87,
    "criteria_by_source": {"Zennify SDD standard": 57, "Well-Architected": 33},
    "critical_floor_active": ["2A.story_coverage_complete", "3B.record", "..."],
    "calibration_content_path": ".../zms-calibration-content.json",
    "calibration_summary_path": ".../zms-calibration-summary.json",
    "sa_reasoning_playbook_path": ".../references/sa-reasoning-playbook.md"
  },
  "release_awareness": {
    "findings_path": ".../release-awareness-{a|b}.json",
    "rr_deductions_capped_total": -8,
    "recommended_successors": 5
  },
  "content_mapping": {
    "dim_4_floor_cap": null,
    "stub_missing_count_over_8_required": 0,
    "component_classifications": []
  },
  "run_integration_heavy": false,
  "applicability_flags": {
    "INTEGRATIONS": true, "EXTERNAL_USERS": false, "MULTI_CLOUD": false,
    "REGULATED": true, "REGULATORY_CITATION": true, "AUTOMATION": true,
    "TRIGGERS": true, "CUSTOM_BUILD": true, "UI_IN_SCOPE": true,
    "CONFIG_DRIVEN": false, "API": true, "DATA_MIGRATION": true, "PHASING": true
  }
}
```

## Output bundle: field summary

The full output-bundle JSON schema and worked example live in `section-d-bundle-schema.md`; read it when assembling/merging the lane bundle at the end of sub-batch 4b (Output A) or 4d (Output B). While scoring, record per sub-criterion: `scores` (5 passes), `mean`, `stddev`, `variance_flag`, `content_coding.zms_components[]` (criterion id, component, verdict, evidence anchor), `zms_calibration_citations[]` per dimension, `per_dim_key_reasoning` (BRD citations on Dims 1/2/6), deduction blocks (Dim 3 RR/TRUST), and the verbatim non-bias attestation.

## Bundle validation: what Section E enforces

R1-R25 run in `score_sheet_populate.py` at Section E; you do not self-validate the whole rule set while scoring. The rules with in-scoring behavioural force are: R11 (truth-source firewall; see banned/allowed phrasings in `section-d-bundle-schema.md`), R16 (verbatim attestation), and the citation-presence rules (every dimension cites ZMS; Dims 1/2/6 also cite the BRD). Full rule text: `section-d-bundle-schema.md`.

## Five-run discipline (genuinely independent, one pass per turn)

Five independent scoring passes per dimension, **each scored in its own cold turn** (a fresh context per pass — independence comes from the one-pass-per-turn protocol plus `pass_plan` decorrelation, not from any sampling parameter) and written to its own file via `pass_accumulate.py record` (`<run>/passes/<lane>_<group>_passN.json`). No turn ever holds more than one pass; the five-element array is assembled only by `pass_accumulate.py aggregate` reading the five files from disk. This is what makes the passes genuinely independent and the resulting `stddev` a real pass-to-pass stability signal rather than single-turn theatre. In each pass-turn:

- Read SDD passages from scratch (cold); do not consult any earlier pass's file.
- Re-anchor to the operator BRD as the requirements truth source on all 7 dimensions; additionally re-anchor to the relevant technical truth source where applicable (Salesforce platform standards on Dim 3; Content Mapping on Dim 4; release-awareness findings on Dim 3).
- Re-consult ZMS calibration content (`zms-calibration-content.json` and the SA reasoning playbook) on all 7 dims.
- Re-derive band and within-band score, then `record` this pass.

After all five passes of both dim-groups for a lane are on disk, `pass_accumulate.py aggregate` computes, per dimension:
- `mean = round(sum(scores)/5, 1)`
- `stddev = round(statistics.stdev(scores), 2)` (sample, n−1)
- `band` = `contracts.band_for_pct(100 * mean / max)` (mean-derived; see band authority below)
- `variance_flag = stddev > 1.0`

and the per-sub-criterion five-pass arrays and the modal verdict per criterion. Merge these into the lane bundle.

**Band authority.** The **authoritative** quality band on the score sheet
is derived deterministically from the dimension mean as a percentage of max,
using the four-band scale in `contracts.BAND_SCALE` (rubric §3:
STRONG ≥80 / GOOD 70–79 / ADEQUATE 65–69 / WEAK <65), so
the band, the gate, and the score can never disagree on the sheet. The quality
band is a separate axis from the qualification **gate** (rubric §8, aligned 1:1
with the bands: PASS ≥80% / MARGINAL_PASS 70–79% / MARGINAL_FAIL 65–69% / FAIL
<65%); never report a band word as an accept/reject decision.

**Never re-run a pass to chase a different number.** Variance is the uncertainty signal. The only legitimate re-run case: a pass produced a blinding leak or a truth-source contamination — discard that pass file and re-record it with `--force`; do NOT re-run other passes.

Each pass is a distinct reasoning episode in its own turn, starting from first principles (truth source → ZMS calibration → observable criteria → band → score) rather than from a prior episode's result.

## Pass decorrelation, lane counterbalancing, and adversarial self-check (v4.5)

Even with each pass in its own cold turn, a single mind can still walk the
criteria the same way each time and settle into a repeated path, which biases
`stddev` low. Decorrelate the passes deterministically using
`pass_plan.pass_plan(run_id, criteria_ids)`, which is reproducible from the
run_id and assigns, per pass-turn:

- a distinct **criterion order** (so no two passes walk the criteria in the same
  sequence) — re-anchor and re-derive in that order;
- a **lane_first** that alternates A,B,A,B,A — when scoring the run as a whole,
  do **not** always score Output A before Output B; counterbalancing removes the
  position/anchoring bias that inflates the first-scored lane;
- a rotating **framing** (neutral / strict / literal / skeptical / charitable) —
  hold the evidence fixed but vary the reading stance, so the spread across
  passes reflects genuine judgement uncertainty, not a single repeated path.

This changes nothing about the deterministic scoring math; it makes the
five-pass spread measure something real, so the variance flag is trustworthy.

**Adversarial self-check on high-risk verdicts.** Self-agreement bias makes a
single mind tend to confirm its own first reading. Before the bundle is written,
call `pass_plan.challenge_targets(verdicts_by_criterion, critical_floor_ids)` —
passing the ZMS register's `critical_floor_ids` — to select the **bounded**
high-risk set: every **critical-floor** criterion scored Present (a wrong Present
here masks a critical gap) plus every **non-unanimous** criterion. Re-read each
selected criterion against its **strongest counter-argument** from the same
evidence — explicitly arguing the weaker verdict (Partial/Absent), using the SA
playbook's five shallowness patterns as the prosecution. Record the
post-challenge verdict; `pass_plan.verdict_stability(...)` surfaces any **flip**
(a verdict that did not survive its counter-argument). A flipped verdict is
re-coded to the surviving verdict, not the original. The scope is deliberately
bounded — not every Present — so the challenge adds only a small, fixed number of
re-reads to the heaviest sub-batch (Dims 1-3, ~56 criteria at five passes) and
cannot push that single response past the context-budget guard. A Present that
survives its strongest challenge is materially stronger evidence than one taken
at first sight. This adds no second model — it is a second, adversarial framing of
the same evaluator.

## Blinding (OH §3.3)

Reference the SDD only as "Output A" / "Output B" / "this SDD" / "the candidate SDD". Never narrate, infer, or imply lane identity. No occurrence of `ZenAgent | ZennAgent | ZA | off-the-shelf | OTS` anywhere in any reasoning, narrative, attestation, sub-criterion reasoning, or ZMS-citation observation field.

## Truth-source separation table

| Dim | Requirements truth source | Technical truth source | ZMS as requirements authority? | ZMS as calibration reference? |
|---|---|---|---|---|
| 1 BRD Comprehension | Operator BRD | n/a | NO (R11 + R18 enforce) | YES |
| 2 Requirement Coverage | Operator BRD | n/a | NO (R11 + R18 enforce) | YES |
| 3 Salesforce Solution Fit | Operator BRD | Salesforce platform standards + rubric §7.1/§7.2 deduction schedules + release-awareness findings | NO | YES |
| 4 Design Specificity | Operator BRD | Content Mapping (structural) | NO | YES |
| 5 Dependencies and Assumptions | Operator BRD | Delivery and implementation principles | NO | YES |
| 6 Scope Discipline | Operator BRD | n/a | NO (R11 + R18 enforce) | YES |
| 7 Estimation Readiness | Operator BRD | Evidence and auditability requirements | NO | YES |

## ZMS calibration procedure (all 7 dimensions)

Per dimension, per pass:

1. **Identify the operator BRD requirements relevant to this dimension.** Use story IDs, headlines, ACs.

2. **Locate the candidate SDD's response** to those requirements.

3. **Assemble the ZMS calibration bar.** From `zms-calibration-content.json` → `criteria_by_dim_and_sub`, pull the ZMS criteria mapped to the parent sub-criterion(a) being scored on this dimension. For each, read `depth_indicator`, `depth_indicator_components`, `source`, `severity_if_absent`, `critical_floor`. The set of these criteria is the calibration bar for the sub-criterion, the operational "what good looks like" for this run, source-anchored to the ZMS register.

4. **Apply the SA reasoning playbook.** Read `sa-reasoning-playbook.md` fresh; apply the three-step decision protocol (decompose → search → aggregate) to each ZMS criterion that fires. Recognise the five shallowness patterns; apply the three borderline rules where evidence is ambiguous; consult the eight domain heuristics for security/integrations/data model/automation/coverage/scope/estimation/ADRs.

5. **Record a `zms_calibration_citations[<dim>]` entry per criterion that grounds the band**, with FLAT fields (R12 validates these at the entry's top level; do not nest them under a `candidate` object): `{zms_criterion_id, source_label, brd_ref, sdd_ref, verdict, evidence_anchor, observation}`. `verdict` is one of Present/Partial/Absent/NA; `evidence_anchor` is the verbatim ≤30-word SDD quote (Present requires a substantive anchor, R20). The `observation` (≥30 chars) explains how the candidate's content compares to the criterion's depth_indicator components.

6. **Assign the dimension's band** based on the aggregate of ZMS verdicts, applying the rubric's mechanical rules (Trust deductions on Dim 3 per OH §3.6.4; release-awareness deductions per Section C.5 findings; floor cap on Dim 4 per OH §3.5.2; integration-heavy weights on Dim 5/7; multi-cloud applicability per rubric §5; critical-floor cap when an applicable critical-floor ZMS criterion verdicts Absent).

7. **Compile `per_dim_key_reasoning[<dim>]`** referencing content from the ZMS-citation entries that grounded the band assignment. On Dim 1/2/6 the reasoning must additionally cite at least one operator-BRD passage, R18.

Unmatched operator BRD requirements on Dim 3/4/5/7 (no ZMS criterion analogue): note in the diagnostic report's §3 lift-driver decomposition as a *framework-coverage observation*, the ZMS register did not anticipate this requirement. The candidate's choice is not penalised in scoring but the gap surfaces for ZMS v1.x.0 refinement.

## Content-analysis calibration (the "what good looks like" engine)

Scoring is a **content-analysis** procedure, not a holistic impression. Each sub-criterion is scored by *coding* the candidate SDD's text against the ZMS criteria that map to that sub-criterion. The ZMS criterion is the unit; its `depth_indicator_components` are the things to search for; the verdict (Present / Partial / Absent / NA) is the coded result; the aggregate verdict distribution drives the sub-criterion's within-band score. This makes "what good looks like" an explicit, inspectable artefact, the ZMS criteria define the bar at the v4.6 freeze, rather than a number the evaluator asserts.

### Coding scheme structure

For every sub-criterion the scheme defines three things:

1. **Categories**, the ZMS criteria mapped to the parent sub-criterion via `zms-22-mapping.json`. These are the observable units that must verdict Present for the sub-criterion to be satisfied. (For example, sub-criterion `3B` Trusted Design has 12 ZMS criteria as categories: `3B.org`, `3B.object`, `3B.field`, `3B.record`, `3B.action`, `3B.apex`, `3B.integration_user`, `3B.external_user_exposure`, `3B.auditability`, `3B.encryption_shield`, `3B.data_retention`, `3B.regulatory_control_mapping`.)
2. **Indicators**, each ZMS criterion's `depth_indicator_components` define what realises that category. Components are mechanism-level (named Salesforce mechanism, named artefact, quantified value, explicit decision with rationale). Product-level mentions without the named component do **not** satisfy an indicator. The SA reasoning playbook (Section 1, the three-step protocol) is how indicators are evaluated.
3. **Evidence anchors**, every Present verdict requires an SDD anchor: a verbatim passage (section reference + quote ≤ 30 words) OR an unambiguous section reference where the component is concretely specified. A criterion the SDD addresses at mechanism level is **Present** even if the wording is paraphrased rather than quotable, provided the anchor points to where it is specified. A criterion the SDD references but does not specify at mechanism level is **Partial**, not Absent. A criterion is coded **Absent** only when the SDD does not address it at all, or addresses it so generically that no component is realised. This mirrors how a senior architect reads a real SDD: credit is given for substantive coverage, not withheld for imperfect phrasing. R20 enforces that Partial/Absent verdicts on Zennify-source criteria carry an anchor documenting what was searched for.

### The coding procedure (per sub-criterion, per pass)

1. **Identify which ZMS criteria fire for this sub-criterion.** From `zms-calibration-content.json` → `criteria_by_dim_and_sub[<dim>][<sub>]`. The applicable list is the calibration bar.
2. **For each criterion in the bar**, apply the SA playbook's three-step decision protocol: decompose `depth_indicator_components` → search SDD for each component → aggregate to verdict (Present / Partial / Absent / NA). NA applies when the criterion's `applicability` flag does not fire for the engagement (already filtered upstream by ZMS loader; should not appear in the bar at scoring time).
3. **Compute the coverage signal.** Coverage = (count of Present) + 0.5 × (count of Partial), divided by total criteria in the bar. Coverage maps to the sub-criterion's within-band score through the **codified curve `coverage_to_score(coverage, max_points)` in `score_sheet_populate.py`**, which is the canonical, version-controlled mapping (the score sheet recomputes it, so a hand-assigned number that disagrees is a validation error). The curve is calibrated to how a senior architect grades a real design: coverage ≥ 0.85 → top of band (a design that addresses the large majority of components at mechanism level is genuinely strong and scores in the 80s+); 0.70 → 80% (Strong floor); 0.50 → ~68% (Adequate/Good); below 0.30 → floor. It is intentionally not linear-from-zero: a design covering most of the bar substantively earns a high score rather than being dragged down by a few imperfect components, because that is what a good SDD looks like in practice. Critical-floor ZMS criteria still matter when Absent, but the cap is realistic, not punitive: an Absent critical-floor criterion caps the sub-criterion at the **Good band boundary** (the `critical_floor_absent=True` path), rather than forcing it below the Adequate line. One missing critical component constrains the ceiling; it does not by itself condemn an otherwise sound design.
4. **Record the coding.** Persist the coded result in the sub-criterion's `content_coding` block (schema in §2). The coding *is* the evidence trail behind the score; `reasoning` summarises it in prose, and the relevant Present/Partial/Absent verdicts become `zms_calibration_citations` observations.

### Coding rules

- **ZMS-relative, not absolute.** The calibration bar is the set of ZMS criteria that fire per the engagement's applicability flags. Criteria the engagement doesn't require (`NA`) are excluded from coverage calculation. The candidate is calibrated to the ZMS bar at the v4.6 freeze, never to an idealised checklist beyond it.
- **Evidence-anchored, realistically read.** A criterion is Present when the SDD specifies it at mechanism level with an anchor (verbatim quote or a precise section reference), Partial when it is addressed but not specified to mechanism level, and Absent only when not addressed or addressed so generically that no component is realised. The anchor keeps "what good looks like" inspectable; it is read the way a senior architect reads a real SDD, crediting substantive coverage rather than penalising imperfect phrasing.
- **Mechanism-level discriminates Present from Partial.** This is the single most important coding decision and the main driver of band separation between an SA-grade SDD and a generic one. The SA playbook's five shallowness patterns (platform asserter, generic placeholder, token vocabulary, unsupported assertion, displaced answer) are the specific shapes of Partial-or-Absent verdicts.
- **Deterministic categories, judged components.** The ZMS criteria mapped to each sub-criterion are fixed at the v4.6 freeze; whether each criterion's depth_indicator components are met is the judged part and is where five-pass variance legitimately arises.
- **Coding precedes the number.** Assign the within-band score from the coded coverage; never assign a score first and back-fill coding.
## SA-grade evaluation discipline

The rubric's STRONG band requires, on all dimensions:

- Citation density: every band cites specific SDD passages; ZMS criterion (with source label) cited where it grounded the band via `zms_calibration_citations`.
- Mechanism-level naming over product-level (*"Permission Set Group `Compliance_PSG`"*, not *"Permission Set"*).
- Salesforce Well-Architected priority order on Dim 3: Trusted → Easy → Adaptable.
- ADR format on Dim 4 ADQ: Decision + Context + Options + Rationale + Trade-offs.
- Canonical Salesforce trade-offs on Dim 4: declarative-vs-code, standard-vs-custom, real-time-vs-batch, single-vs-multi-org, phased-vs-big-bang, native-vs-AppExchange.
- Six-layer security on Dim 3 Trusted Design: Org, Object, Field, Record, Action, Apex.

The rubric's format-agnostic principle (§1.4) applies: a required component appearing in a capability module or distributed prose is fully present provided the content is substantive. **Layout or section-naming similarity to any reference is NOT credit**; substance is. The ZMS criteria measure substance, not format.

## Self-validation before writing the bundle

- [ ] `five_runs_by_dimension` has 7 keys, each list of exactly 5 numerics
- [ ] `per_dim_mean`, `per_dim_stddev`, `per_dim_variance_flag` recompute correctly
- [ ] All 7 `per_dim_band` values in `{STRONG, GOOD, ADEQUATE, WEAK}`
- [ ] `per_dim_truth_source` matches §2 schema verbatim (ZMS-aware)
- [ ] Dim 3 sub-criteria: 4 (or 5 if multi-cloud); reasoning ≥50 chars each
- [ ] Dim 4 sub-criteria: `floor_cap` matches input; `final_dim_4_score` consistent
- [ ] Every deduction has `id`, value ∈ {−1, −3, −5} (TRUST severity tiers: Minor −1 / Major −3 / Critical −5. RR/release under the binary RR model is only −1 for `in_force_unverified` when the live path ran, or −3 for any confirmed-not-in-force status; RR no longer emits −5), `triggering_passage`, `salesforce_source`
- [ ] **R19 satisfied: every applicable ZMS criterion appears in at least one sub-criterion's `content_coding.zms_components`**
- [ ] **R20 satisfied: every Partial/Absent verdict on Zennify-source criteria carries an evidence_anchor documenting what was searched for**
- [ ] **`zms_calibration_citations[1..7]` non-empty; each entry well-formed with FLAT fields (zms_criterion_id, source_label, brd_ref, sdd_ref, verdict, evidence_anchor, observation ≥30 chars)**
- [ ] **Every scored sub-criterion carries a `content_coding` block: ZMS criteria mapped, candidate Present/Partial/Absent/NA coded per criterion, coverage computed, each Present verdict evidence-anchored with a verbatim quote ≤30 words**
- [ ] **Each sub-criterion score follows from its coded coverage (coding precedes the number; no back-filled coding)**
- [ ] **Per-dim reasoning references at least one zms_calibration_citations entry on each dim 1..7**
- [ ] **Dim 1/2/6 reasoning cites at least one operator-BRD passage (story-ID or section reference), R18**
- [ ] **Dim 1/2/6 reasoning and ZMS-citation observations contain no ZMS-as-requirements-authority phrasings, R11**
- [ ] **R21–R24 satisfied: every TRUST/RR deduction traces to a named schedule entry; every RR deduction has a release_finding_ref matching a finding_id in the bundle's release_awareness_findings; every RR salesforce_source is on the whitelist; every RR deduction has a corresponding Release Currency Audit row (report Appendix B)**
- [ ] No `ZenAgent | ZennAgent | ZA | off-the-shelf | OTS` token anywhere, including sub-criterion reasoning fields
- [ ] `blinding_attestation` signed
- [ ] `non_bias_attestation` signed (v3.7 verbatim, cites ZMS)
