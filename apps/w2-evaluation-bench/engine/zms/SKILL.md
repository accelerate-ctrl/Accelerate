---
name: zms
description: >-
  Zennify Methodology Spec: frozen, versioned calibration reference for Salesforce SDD evaluation. Provides a source-labelled calibration bar (99 criteria across 7 dimensions / 22 sub-criteria) drawn from Zennify in-house SDD standards and the Salesforce Well-Architected Framework, plus the senior-SA reasoning playbook for arriving at Present/Partial/Absent verdicts. Invoked by evaluate-sdd Section B to filter the criteria to those applicable for the engagement, consumed by Section D as the calibration content, and cited by the diagnostic report's coverage matrix and recommended actions. ALWAYS invoke when an evaluate-sdd run reaches Section B, when a caller needs the ZMS criteria register or the SA reasoning playbook, or when the evaluator needs to determine what good looks like for a Salesforce SDD. Does not score, generate, or handle release-awareness. Pure calibration reference.
license: Internal. Zennify Inc. Confidential.
---

# ZMS: Zennify Methodology Spec (Calibration Skill)

**Version:** 4.5  ·  **Schema:** 4.0.0  ·  **Status:** Frozen

A standalone calibration skill that supplies the "what good looks like" reference for Salesforce SDD evaluation. ZMS replaces the Benchmark Library + exemplar-labelling approach of prior evaluate-sdd versions, the calibration is now a versioned, authored standard backed by two named authorities (Zennify in-house SDD standards + Salesforce Well-Architected Framework) plus the senior-SA reasoning playbook.

## What this skill provides

Three artefacts consumed by callers (primarily the evaluate-sdd skill):

1. **The 99-criterion calibration register** (`data/zms-criteria.json`), every criterion measures substantive content in the SDD. Each carries: ID, name, depth_indicator with decomposed searchable components, source label, parent sub-criterion (one of 22), applicability flag, severity, critical-floor marker.
2. **The 99 → 22 sub-criterion mapping** (`data/zms-22-mapping.json`), every criterion maps to one parent sub-criterion in the rubric's 22-sub-criterion scoring grid. The 99 act as content-analysis categories within each parent's calibration bar.
3. **The senior-SA reasoning playbook** (`references/sa-reasoning-playbook.md`), encoded decision protocol, five shallowness patterns, borderline resolution rules, eight domain heuristics, six anti-bias self-discipline rules, six special-situation handlers. Read fresh at every Section D sub-batch invocation.

## When this skill fires

The orchestrator (evaluate-sdd) invokes this skill at **Section B** of the workflow, replacing the prior `benchmark_select.py`. The invocation contract:

**Input**, applicability flags derived from the operator BRD by `intake_validate.py`, plus the run_id:

```json
{
  "applicability": {
    "INTEGRATIONS": true,
    "EXTERNAL_USERS": true,
    "MULTI_CLOUD": false,
    "REGULATED": true,
    "REGULATORY_CITATION": true,
    "AUTOMATION": true,
    "TRIGGERS": true,
    "CUSTOM_BUILD": true,
    "UI_IN_SCOPE": true,
    "CONFIG_DRIVEN": false,
    "API": true,
    "DATA_MIGRATION": false,
    "PHASING": true
  },
  "run_id": "W2-2026-06-03-xxxxxxxx"
}
```

Note on flags: the loader recognises 14 keys (the 13 intake-derived flags above plus the register-internal `ALL`). `ALL` is not an intake flag; criteria labelled `ALL` always fire. `PHASING` is recognised for forward compatibility but no criterion in the v4.6 register carries it, so it currently filters nothing.

**Output**, two JSON artefacts written to `/pilot-runs/<run_id>/`:

- `zms-calibration-content.json`, the full calibration bundle consumed by Section D. Carries `applicable_criteria` (filtered to those that fire per the flags), `criteria_by_dim_and_sub` (grouped for sub-batch routing), the `sa_reasoning_playbook_path` (so Section D can re-read the playbook fresh), the source distribution summary, and the active critical-floor list.
- `zms-calibration-summary.json`, cover-panel-sized provenance: `zms_version`, `zms_frozen_at`, criteria count, source distribution, active critical floors, fired applicability flags. Surfaces in the Diagnostic Report's calibration-provenance panel.

**Digest emitted to stdout**, the orchestrator captures this for the run record:

```json
{
  "status": "ok",
  "zms_version": "4.6",
  "applicable_criteria_count": 76,
  "criteria_by_source": {"Zennify SDD standard": 47, "Well-Architected": 29},
  "critical_floor_active_count": 6,
  "applicability_keys_fired": ["INTEGRATIONS", "EXTERNAL_USERS", "REGULATED", ...],
  "calibration_content_path": "/pilot-runs/<run_id>/zms-calibration-content.json",
  "sa_reasoning_playbook_path": "<skill_root>/references/sa-reasoning-playbook.md"
}
```

## Invocation

From the orchestrator (evaluate-sdd Section B shim):

```bash
echo '{"applicability": {...}, "run_id": "..."}' | \
  python3 <zms_skill_root>/scripts/zms_load.py --stdin \
    --output-dir /pilot-runs/<run_id>/
```

Or directly with arguments:

```bash
python3 <zms_skill_root>/scripts/zms_load.py \
  --applicability '{"INTEGRATIONS": true, ...}' \
  --run-id W2-2026-06-03-xxxxxxxx \
  --output-dir /pilot-runs/<run_id>/
```

Self-test (run before first use, after any update):

```bash
python3 <zms_skill_root>/scripts/zms_self_test.py
```

## How Section D uses the output

For each sub-batch (4a Output A Dims 1-3, 4b Output A Dims 4-7, 4c Output B Dims 1-3, 4d Output B Dims 4-7), the evaluator:

1. **Reads `sa-reasoning-playbook.md` fresh**, the playbook is not cached across sub-batches.
2. **Reads `zms-calibration-content.json`** for the criteria that fire on the dimensions in this sub-batch.
3. **For each sub-criterion** (one of the 22), assembles the **calibration bar** from the `criteria_by_dim_and_sub` mapping: the ZMS criteria mapped to that parent sub-criterion are the components to search for.
4. **For each ZMS criterion in the bar**, runs the decision protocol (decompose → search → aggregate) and records the verdict (Present / Partial / Absent / NA) with a verbatim ≤30-word evidence anchor for Present verdicts.
5. **Aggregates** the per-criterion verdicts into the sub-criterion's content_coding block; coverage drives the within-band score.
6. **Five-pass discipline at T=0.3** with context resets between sub-batches; variance flag if stddev > 1.0.

The scoring bundle's `content_coding` blocks (one per sub-criterion) carry the full audit trail: which ZMS criteria fired, their source labels, their verdicts, the evidence anchors. This is what the diagnostic report's coverage matrix (Appendix A) and in-house IP gap analysis (Appendix C) surface.

## How the diagnostic report reflects ZMS

Five distinct surfaces in the diagnostic report depend on ZMS data:

- **Calibration Provenance** (run-provenance appendix), ZMS version, freeze timestamp, applicable criteria count, source distribution table, active applicability flags, active critical-floor list
- **ZMS Criteria Coverage Matrix** (coverage-matrix appendix), every applicable criterion, both lanes' verdicts, evidence anchors verbatim. Factually exhaustive: row count == applicable_criteria_count.
- **In-house IP Gap Analysis**, filtered view of the coverage matrix to `Zennify SDD standard` criteria where ZenAgent scored Partial or Absent. Auditable in-house IP gap surface. (The register currently carries no joint-source criteria; if a future ZMS version reintroduces a joint label, those criteria filter in as well.)
- **Recommended Actions**, each action cites the ZMS criterion ID, source label, depth_indicator components, the candidate's actual content (verbatim), and the substantive content required.
- **Per-Dimension methodology-value / lift decomposition**, lift drivers identified by ZMS criterion ID, naming the criteria where the lanes diverged.

The bundle validation gate (R12, R13, R16) enforces that every band assignment cites at least one ZMS criterion with its source label. No band score is admissible without ZMS grounding.

## Composition with evaluate-sdd

ZMS is consumed by evaluate-sdd; it does not invoke evaluate-sdd in turn. The composition is one-way:

```
evaluate-sdd Section B  →  invokes ZMS loader  →  consumes ZMS output
                                                  in Section D scoring
                                                  in Section E score sheet
                                                  in Section G report
```

The ZMS skill is fully usable on its own as a reference for any SDD review, a senior SA reading the criteria register + playbook gets the framework's calibration directly. It does not require evaluate-sdd to function.

## Update governance

ZMS is a **frozen calibration reference**. Updates carry a version bump, freeze timestamp, and CHANGELOG entry. The version + timestamp travel with every run's `zms-calibration-content.json` so reports are reproducible-in-context: an evaluation under an earlier ZMS freeze and one under a later freeze on the same SDDs may differ, but each is auditable against its own frozen calibration.

Update categories:

- **Patch (1.0.x)**, depth_indicator wording refinement, component decomposition improvement, no semantic change
- **Minor (1.x.0)**, new criterion added, source label re-attribution, mapping refinement
- **Major (x.0.0)**, criterion removed, severity reclassification, dimension restructure

The Source Authority document (`references/sources.md`) is updated synchronously with every criterion change.

## Files in this skill

```
zms/
├── SKILL.md                              this file
├── CHANGELOG.md                          version history
├── data/
│   ├── zms-criteria.json                 99-criterion register (machine-readable)
│   └── zms-22-mapping.json               99 → 22 parent mapping
├── references/
│   ├── zms-criteria.md                   99-criterion register (human-readable)
│   ├── sa-reasoning-playbook.md          senior-SA decision protocol + playbook
│   └── sources.md                        authority citations per source label
└── scripts/
    ├── zms_load.py                       invocation entry point (Section B)
    └── zms_self_test.py                  15-check data integrity validator
```

## What this skill does not do

- Does not score SDDs. Scoring is evaluate-sdd Section D.
- Does not generate SDDs.
- Does not check release currency. That is evaluate-sdd Section C.5 (`release_awareness_check.py`).
- Does not interpret applicability flags. Flags come from `intake_validate.py` based on operator BRD content.
- Does not retrieve or analyse the operator BRD. The ZMS is engagement-independent, applicability filtering is the only engagement-aware behaviour.

---

*ZMS skill v4.6, frozen calibration reference for the Solutioning Evaluation Framework. (Renumbered to v4.5 for project-wide version consistency; calibration content unchanged — 99 criteria, B1 and D2 resolved. The data-format schema_version remains 4.0.0.)*
