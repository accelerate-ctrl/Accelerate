# ZMS CHANGELOG

## v4.6 (2026-07-02) — framework version alignment

Renumbered from 4.5 to **4.6** so the calibration register carries the same version label as the v4.6 Solutioning Evaluation Framework refinement (evaluate-sdd, rubric, operations handbook). **No change to calibration content** — all 99 criteria, the 58/41/0 source split, the 7 critical floors, and the 22-sub-criteria mapping are byte-for-byte identical to the 4.5 (= 4.0 = 1.1.0) freeze; `frozen_at` is unchanged. The ZMS data-format `schema_version` (4.0.0) is unchanged; only `zms_version` and this label move to 4.6.

## v4.5 (2026-06-30) — framework version alignment

Renumbered from 4.0 to **4.5** so the calibration register carries the same version label as the rest of the v4.5 Solutioning Evaluation Framework (evaluate-sdd, rubric, operations handbook). **No change to calibration content** - all 99 criteria, the 58/41/0 source split, the 7 critical floors, and the 22-sub-criteria mapping are byte-for-byte identical to the 4.0 freeze. The ZMS data-format `schema_version` (4.0.0) is unchanged; only `zms_version` and this label move to 4.5.

## v4.0 (2026-06-17) — project-wide version consolidation

Renumbered from 1.1.0 to **4.0** so the calibration skill carries the same major version as the rest of the Solutioning Evaluation Framework (evaluate-sdd, system prompt, rubric, operations handbook, framework document). Schema bumped to 4.0.0; re-frozen at 2026-06-17.

**No change to calibration content.** All 99 criteria, the 58/41/0 source split, the 7 critical floors, and the 22-sub-criteria mapping are byte-for-byte identical to the prior 1.1.0 freeze. This is a label change for version consistency, not a recalibration. Evaluations run under 1.1.0 remain comparable; only the version string and freeze timestamp differ.


## v1.1.0 documentation errata (register untouched; no version bump)

The frozen register (`data/zms-criteria.json`, `data/zms-22-mapping.json`), the playbook, and the loader are UNCHANGED; runs remain reproducible against v1.1.0. Errata fixed in documentation only:

- SKILL.md: "94 -> 22" corrected to "99 -> 22" (two places); digest example updated to v1.1.0 with real source labels (no joint-source criteria exist at v1.1.0); self-test described as 14-check (was "12-check"); "ZennAgent" typo corrected; diagnostic-report surface references mapped to the concise builder (Appendix A/C/E, Sections 2-3) with legacy template numbering retained as alias; added a note that `ALL` is register-internal (not an intake flag) and `PHASING` is recognised but carries zero criteria at v1.1.0.
- references/zms-criteria.md: critical-floor summary list corrected — `3B.record`, `3B.external_user_exposure`, and `4A.security_sharing_model` are labelled `Well-Architected` in the register, not `Zennify + Well-Architected` (the joint label is reserved and empty). Per-criterion entries were already correct.

Self-test extended with check 15 (zms-criteria.md source-label annotations diffed against the register — the guard that would have caught the floor-list mislabelling). Re-run after errata: 15/15 green.

---


## v1.1.0 (register completeness: ratified & frozen)

**Status:** Frozen calibration reference. Ratified by senior SA: the 5 completeness criteria are approved; QA item D2 (critical-floor expansion) reviewed and resolved, the 7 conservative floors are retained as the deliberate baseline (no expansion). This is the deployment baseline.

### Why

Stage 2 completeness audit found quality components a senior SA expects in a strong Salesforce SDD that the v1.0.x register could not detect at all, most importantly four of evaluate-sdd's own `THE_EIGHT_REQUIRED` components had a presence-floor check but **no quality criterion** in ZMS. A gap ZMS cannot see is a gap the evaluation cannot flag, even when an off-the-shelf SDD includes it and the ZenAgent template omits it, precisely the IP-expansion signal the evaluation exists to surface.

### What changed (94 → 99 criteria)

Five criteria added, each mapped to an existing sub-criterion (no rubric, grid, dimension, or schema change, this is why it is a minor bump, not major):

- **`4A.reporting_analytics`** (Zennify SDD standard, ALL), report types, key reports/dashboards, analytics audience/access. Closes the Reporting and Analytics Design required-component gap.
- **`4A.business_process_flows`** (Zennify SDD standard, ALL), each in-scope process described trigger-to-outcome with the responsible persona/system. Closes the Business Process Flows required-component gap; distinct from 3C automation mechanism.
- **`4A.open_decisions_log`** (Zennify SDD standard, ALL), unresolved decisions surfaced with owner + impact. Closes the Open Decisions Log required-component gap.
- **`4A.confidence_annotations`** (Zennify SDD standard, ALL), provisional design elements marked, tied to specific sections. Closes the Confidence Annotations required-component gap; complements the content-mapping stub rule already in content_mapping_classify.py.
- **`3C.async_volume_strategy`** (Well-Architected, Adaptable, AUTOMATION), async processing (Batch/Queueable/Scheduled) chosen and justified when volume/long-running work warrants. Distinct from 3C.bulk_behavior and 3C.transaction_boundaries.

Source distribution after additions: **58 Zennify SDD standard / 41 Well-Architected / 0 joint** (was 54 / 40 / 0). 4A now holds 14 criteria; 3C holds 11. Critical floors unchanged (7).

### What was deliberately NOT added

The audit rejected 10 candidate areas as over-reach or out of an SDD's scope (governor-limit enumeration, deployment/CI-CD, duplicate rules as standalone, LDV sharing skew, mobile/offline, accessibility/localization, AI/Einstein static criteria, success-metrics/UAT, notifications, dollar costing). Rationale recorded in the Stage 2 analysis. Over-adding would penalise good SDDs on things a senior SA would not require, introducing the very bias the framework guards against.

### Ratification gate

Additions change what the evaluation measures, so they require senior-SA sign-off before freeze, exactly as B1 did. On ratification: change SKILL.md status Proposed → Frozen, set a freeze timestamp, and the evaluate-sdd dependency pin moves 1.0.1 → 1.1.0 (minor bump cascades to diagnostic report §4 automatically; no evaluate-sdd logic change required).

### Tests

Self-test 14/14 on the candidate (the alignment guard correctly blocked the candidate until sources.md and zms-criteria.md were updated to match, demonstrating the Stage 1 guard working). Cross-skill seam verified; all 5 new criteria confirmed flowing into Section D calibration content.

---

## v1.0.1 (source-authority alignment: B1 resolution)

**Status:** Frozen calibration reference. Patch release: re-attribution of source labels only, no criterion added, removed, or re-scored; verdict logic and applicability unchanged.

### Why

QA audit item **B1** (deferred for SA review at v1.0.0) is now resolved per SA direction: **Zennify adds no incremental substance on top of the Well-Architected Framework.** The v1.0.0 register labelled every WA-touching criterion `Zennify + Well-Architected`, which over-claimed Zennify authorship of canonical Salesforce guidance and weakened the diagnostic report's defensibility ("that's not Zennify IP, it's Salesforce's own guidance"). A finding rests on the strongest authority only when the label is honest.

### What changed

- **Source re-attribution (42 criteria).** Every criterion previously `Zennify + Well-Architected` was re-examined criterion-by-criterion. Outcome: **40 → `Well-Architected`** (canonical Salesforce guidance, no Zennify increment) and **2 → `Zennify SDD standard`** (`1B.persona_record_visibility` and `4B.simpler_alternative`, genuine SA-review patterns that `sources.md` itself had always described as in-house IP). The `Zennify + Well-Architected` bucket is now **empty** (label retained in schema for a future genuine incremental-Zennify requirement).
- **Source distribution** recomputed: **54 Zennify SDD standard / 40 Well-Architected / 0 Zennify + Well-Architected** (was 52 / 0 / 42).
- **`well_architected_pillar` corrected** to a single canonical pillar (Trusted | Easy | Adaptable) on every WA criterion. Fixes two v1.0.0 prose/data contradictions: `4A.security_sharing_model` (sources.md said Trusted, data said Easy → now Trusted) and `1A.sf_mechanism_named` (sources.md listed it under WA Easy, data was Zennify-pure → confirmed Zennify-pure, removed from WA listing).
- **`references/sources.md` rewritten** as the aligned single source of truth: three real buckets, every pillar/label matching the register exactly, an explicit statement that Zennify adds no incremental substance on top of WA, and the in-house-IP bucket framed as template-driven + SA-review-pattern + quality-bar requirements (the bucket the evaluation measures and grows).
- **`references/zms-criteria.md`** per-criterion `Source` lines regenerated from data; source-distribution and legend updated; the `★` beyond-template marker legend corrected to mean "the template does not elicit this depth" (an axis independent of `source`) rather than "in-house IP".
- **Self-test extended 12 → 14 checks.** New check 13 (source/pillar consistency) and check 14 (sources.md ↔ register alignment via `scripts/sources_alignment_check.py`). Drift between the human-readable authority doc and the machine register now fails the self-test, and therefore the evaluate-sdd preflight.

### Critical floors, verdicts, scoring: unchanged

The 7 critical floors are preserved (floor severity is independent of source authority). No depth_indicator, component, applicability flag, mapping, or playbook rule changed. A v1.0.0 and a v1.0.1 evaluation of the same SDDs produce the same verdicts and scores; only the **authority cited** for each finding changes (more honest, more defensible).

---

## v1.0.0 (initial release)

**Status:** Frozen calibration reference, released for evaluate-sdd v3.7+.

### Provenance

ZMS v1.0.0 replaces the Benchmark Library + exemplar-labelling approach of evaluate-sdd v3.6 and earlier. The substitution is a deliberate architectural shift, motivated by three observations:

1. **The Library was a bottleneck.** Admitting new Library entries required senior-SA panel work that was the slowest step in framework operations. ZMS removes the bottleneck by replacing engagement-paired exemplars with a versioned authored standard.
2. **Exemplars embed bias.** Each Library entry calibrates to its own quality level; mixed-quality entries pulled all candidate scores toward the entry's band. ZMS uses a frozen reference bar across all runs, eliminating the entry-quality drift.
3. **In-house IP needed source-anchored citation.** Senior-SA-asserted gaps in prior diagnostic reports were not auditable. ZMS criteria carry explicit source labels (`Zennify SDD standard` / `Well-Architected` / `Zennify + Well-Architected`) so every gap claim traces to a named authority.

### Composition

- **94 criteria** mapped across **7 dimensions** / **22 sub-criteria**
- **52 criteria** from Zennify SDD standard (in-house IP)
- **42 criteria** from Zennify + Well-Architected (both authorities converge)
- **0 criteria** from Well-Architected alone (reserved for v1.1.0 if pure-Well-Architected criteria are needed)
- **7 critical-floor criteria** preserved from the v5.2.0 register

### Senior-SA reasoning playbook

The playbook captures what a senior Salesforce Solution Architect does mentally when reviewing an SDD, encoding:

- The three-step decision protocol (decompose depth_indicator → search SDD → aggregate verdict)
- Five shallowness patterns (platform asserter, generic placeholder, token vocabulary, unsupported assertion, displaced answer)
- Three borderline-resolution rules (Present-vs-Partial, Partial-vs-Absent, Applicable-vs-NA)
- Eight domain reasoning heuristics (security & sharing, integrations, data model, automation, requirements coverage, scope discipline, estimation readiness, architectural decisions)
- Six anti-bias self-discipline rules (independent lanes, criterion reset, verbatim depth_indicator citation, drift sample-check, no verbosity reward, no polish reward)
- Six special-situation handlers (mutual misses, length agnosticism, bonus-depth handling, internal contradictions, token boilerplate, Salesforce technical truth)

The playbook is what makes ZMS able to handle the exemplar's role without exemplars, the LLM applies the SA's reasoning patterns directly to each criterion at scoring time.

### Component decomposition

Every criterion's `depth_indicator_components` field lists the 1–6 specific things to search for in the SDD. 69 of 94 criteria have ≥2 components (curated by hand for high-stakes criteria); the remaining 25 are genuinely atomic depth_indicators where a single component is correct.

### Schema version

- `zms-criteria.json` schema 1.0.0
- `zms-22-mapping.json` schema 1.0.0
- `zms-calibration-content.json` (loader output) schema 1.0.0
- `zms-calibration-summary.json` (loader output) schema 1.0.0

### Integration contract

The loader (`scripts/zms_load.py`) accepts applicability flags + run_id, filters criteria, emits the calibration bundle for Section D and the summary for §4 of the diagnostic report. Recognised applicability keys: `ALL`, `INTEGRATIONS`, `EXTERNAL_USERS`, `REGULATED`, `REGULATORY_CITATION`, `AUTOMATION`, `TRIGGERS`, `CUSTOM_BUILD`, `UI_IN_SCOPE`, `MULTI_CLOUD`, `CONFIG_DRIVEN`, `API`, `DATA_MIGRATION`, `PHASING`.

### Self-test

12 integrity checks (`scripts/zms_self_test.py`):

1. ZMS data file valid JSON with required top-level fields
2. Criteria count matches declared count
3. Every criterion has required fields
4. Every depth_indicator_components is non-empty
5. Every parent_sub_criterion in canonical 22
6. Every applicability flag in recognised set
7. Every source label in recognised set
8. critical_floor implies severity Critical
9. 22-mapping reverse_mapping consistent with criteria
10. Forward mapping covers all 94 criteria
11. Loader exits 0 on minimal valid invocation
12. Loader output passes schema check

All checks PASS at v1.0.0 freeze.

### What this version does not yet include

- **Pure Well-Architected criteria.** v1.0.0 sources all criteria from Zennify SDD methodology (with WA overlay on 42). v1.1.0 may add criteria that originate purely from Well-Architected without a Zennify equivalent.
- **Multi-flag applicability boolean logic.** Each criterion carries a single applicability key. v1.1.0 may introduce composite expressions (e.g., `INTEGRATIONS AND REGULATED`).
- **Per-dimension quality annotations.** Removed from v1.0.0 (ZMS is a frozen bar; quality is the bar, not a per-run variable). Reserved for future use only if a strong motivating case emerges.

---

*ZMS Change Log, initial release. Future entries will document criteria additions, source re-attributions, and playbook refinements.*
