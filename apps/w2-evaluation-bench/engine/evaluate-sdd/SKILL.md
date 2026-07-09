---
name: evaluate-sdd
description: >-
  Operator-facing skill for Workflow 2 of Zennify's Salesforce Solutioning Evaluation Framework. Evaluates Salesforce Solution Design Documents (SDDs) against the frozen ZMS calibration reference, with a live release-currency crosswalk. Two modes, auto-detected at intake: Mode A (Comparative) scores two SDDs (off-the-shelf vs ZenAgent) blinded across the 7 rubric dimensions and produces a Diagnostic Report carrying the methodology lift; Mode B (SDD Review) reviews ONE SDD qualitatively and produces a build-ready judgement plus prioritised recommendations (no scoring or lift by default). ALWAYS use this skill when the operator mentions evaluate-sdd, evaluate SDD, score SDD, review an SDD, SDD review, Workflow 2, W2, methodology lift, ZenAgent vs off-the-shelf, diagnostic report, ZMS scoring, SDD evaluation, or solutioning evaluation, or supplies a BRD plus one or two SDDs. Depends on the ZMS skill. Does not generate SDDs.
license: Internal. Zennify Inc. Confidential.
---
# evaluate-sdd v4.6

Two modes, one engine. Numbers, verbatim strings, and the floor/gate/band/deduction schedules are single-sourced in `scripts/contracts.py`; docs quote it. Deep per-batch procedure lives in `references/`, loaded per the map below — this SKILL.md is the only always-loaded doc, so keep everything else on disk until its batch needs it.

- **Mode A — Comparative (W2):** two SDDs (ZenAgent vs off-the-shelf), scored blind across the 7 rubric dimensions → lift-bearing **Diagnostic Report**.
- **Mode B — SDD Review:** ONE SDD (any origin) read against the ZMS senior-SA calibration → qualitative **SDD Review Report** (build-ready judgement + prioritised recommendations sourced from the ZMS depth_indicator). No scoring/blinding/lift by default (`--enable-single-scoring` opts in). Origin is a report label only, never a finding.

Auto-detected at intake: two SDDs → A; one → B. Shared engine: ZMS load, content mapping, live release crosswalk, SDD-reading discipline. If ambiguous, confirm once.

## Load map (read only what the batch needs; discard after its digest is on disk)
| Batch | Read |
|---|---|
| 0–2 setup | `references/pipeline-procedures.md` §A–B |
| 3–3.5 mapping | procedures §C, §C.5; `references/release-awareness.md`; `salesforce-docs-mcp.md` (optional) |
| 4a/4c pass-turn | `section-d-core.md` + `section-d-dims-1-3.md` + `zms-calibration-dims-1-3.json` + that lane's SDD + playbook |
| 4b/4d pass-turn | `section-d-core.md` + `section-d-dims-4-7.md` + `zms-calibration-dims-4-7.json` + that lane's SDD + playbook; add `section-d-bundle-schema.md` at bundle assembly |
| aggregate / 4e / 5–8 | digests only; procedures §E,§F,Reveal,§G as each batch runs |

Scripts read big files; you read their stdout digests. Never `cat` an SDD, calibration JSON, or workbook into chat. Never co-load both dim-groups, both SDDs, or both lanes' matrices. Keep live context < ~40k; if one SDD > ~15k tokens, work it in sections via shell.

## Stages and stops
**Mode A** — 15 batches / 6 stages; only **D.5 is a mandatory stop**. S2 and S4 stops are optional operator reviews — default to auto-continue unless asked.
| Stage | Batches | Ends |
|---|---|---|
| S1 Setup | 0 preflight · 1 intake · 2 ZMS load · 2.5 self-consistency check | auto (HALT if a gate blocks) |
| S2 Mapping | 3a/3b content-map · 3.5a/3.5b crosswalk | STOP (optional) |
| S3 Scoring | 4a,4b,4c,4d — each = FIVE turns (one per pass), then aggregate per lane | auto |
| D.5 | 4e checkpoint | **STOP (mandatory)** |
| S4 Sheets+Lift | 5a/5b sheets · 6 lift | STOP (pre-reveal) |
| S5 Reveal+Report | 7 reveal · 8 report | done |

**Mode B** — single lane, no blinding/scoring/lift: S1 setup → S2 mapping (one lane) → S3 review (R1 dims1-3, R2 dims4-7; ZMS as lens) → S4 build SDD Review Report. `--enable-single-scoring` adds a numeric annex via the Mode A machinery (opt-in).

Within a stage: run script → digest to disk → discard raw → next script, same response. Budget guard overrides bundling: near ~40k, stop at the boundary and name the last batch.

## Hard rules
1. **Discard between batches** — carry forward only digests + paths.
2. **Five GENUINELY INDEPENDENT passes, one per turn** — read the SDD + slice cold each pass; end the turn with `pass_accumulate.py record` (one file per pass, never a 5-element array); don't peek at an earlier pass; re-record refused without `--force`. Aggregate per lane after all five. Variance flag at stddev>1.0. Lift only in Section F.
3. **On context pressure, STOP** at a batch boundary; resume from digests.
4. **Never fabricate** — missing field → emit `null` and STOP. R1–R25 reject fabricated bundles anyway.
5. **Run the phase gate** from `scripts/pipeline_integrity.py` at each boundary; on `halt`, STOP and surface it. Model-judgment phases are gated on structure/integrity only, never "accuracy".

## Preflight (batch 0)
Resolve, do not read in full. **Knowledge-base docs** (read-as-text, mandatory): `rubric-v4.6.docx`, `operations-handbook-v4.6.docx` — search `/mnt/knowledge/`, `/mnt/project/`, `/knowledge/`, run dir, operator path; take first hit by name prefix (version-tolerant). Missing → HALT with the file, locations searched, and remedy (upload to KB / paste / give path). **Lazy load:** confirm availability only; every operational number is in `contracts.py` + references — read a rubric/handbook section only to adjudicate a specific conflict, never ~10k tokens of prose to start. **In-skill templates** (ship in `assets/`, scripts default to them): `content-mapping-template-v4.6.xlsx`, `score-sheet-template-v4.6.xlsx` — missing = corrupt package (re-install), not a KB upload. **References + ZMS sibling** must exist (missing = corrupt package). ZMS shim cascade: `--zms-skill-root` > `ZMS_SKILL_ROOT` > `../zms` > `/mnt/skills/user/zms` > `/mnt/skills/organization/zms`; `zms_self_test.py` must exit 0. There is no diagnostic-report template — reports are built in code (`report_build_substantive.py`, `report_build_sdd_review.py`, branded via `report_style.py`).

## Blinding (Mode A only) — real isolation
`intake_validate.py` writes the ZenAgent↔Output mapping to `.lane-mapping` ONLY (kept out of stdout and `section-a-output.json`). From Section B to Section F work with unknown Output A / Output B: **do not open the escrow, infer identity, or reason about it before batch 7.** `lane_reveal_apply.py` is the first/only reader. R14 leak: no `ZenAgent`/`ZennAgent`/`ZA`/`off-the-shelf`/`OTS` token before reveal, and no identity via branding, logos, headers/footers, or vendor/product names — quote only substantive design content for anchors. Operator brand/product names go via `--blinding-extra-terms`. A leaked token = contaminated bundle → STOP and regenerate. Mode B has one lane; blinding does not apply.

## Truth-source firewall (R11)
Requirements truth = operator BRD (Dims 1,2,6 must cite it). Technical truth = Salesforce standards + release findings (Dim 3), content mapping (Dim 4 structure). Calibration bar = ZMS, never authority over requirements. Exact banned/allowed phrasings + verbatim `per_dim_truth_source` strings: `section-d-bundle-schema.md`.

## Pipeline: script per batch
Templates auto-resolve from `assets/`. Full inputs/outputs/digest-fields/HALT conditions: `references/pipeline-procedures.md` (read per the load map).

| B | Script |
|---|---|
| 1 | `intake_validate.py --input-artefact <brd> ( --candidate-a <f1> --candidate-b <f2> --zenagent-is a\|b  [neutral, preferred] \| --ots-sdd <ots> --zennagent-sdd <za> \| --single-sdd <sdd> [--single-sdd-origin ...] [--enable-single-scoring] ) --evaluator-model <m> --output-dir <run>` — auto-detects mode; 13 applicability keys; BRD SHA-256; lane escrow (A only: per-label origin+path); emits non-secret `lane_files` (label→path) — the binding batches 3–6 use to pick each lane's SDD |
| 2 | `echo '{"intake_output_path":"...","run_id":"..."}' \| zms_load.py --stdin --output-dir <run>` — self-tests + writes calibration content, summary, dim-group slices |
| 2.5 | Score each `data/accuracy-validation-set.json` case by its `criterion_id` with the SAME verdict procedure → predictions.json → `accuracy_gate.py --predictions predictions.json --output <run>/accuracy-gate.json`. Self-consistency only; predictions file is a FLAT `{case_id: verdict}` map. `block` → HALT (enforceable only once the validation set carries ≥30 cases with ≥50% human/expert labels — the shipped set is advisory-only by construction); `advisory` → continue with a coverage caveat. Pass `--accuracy-gate` to batch 8. |
| 3 (A: 3a/3b) | `content_mapping_classify.py --components-json <c> --blinding-label "Output A\|B" --workbook <out.xlsx> --output <out.json>` — 8 required components; Dim-4 floor via `contracts.dim_4_floor_cap` (0 none / 1–2 cap 10 / 3+ cap 7) |
| 3.5 | `release_crosswalk.py extract --sdd-path <sdd> --lane A\|B --run-id <id> --output-dir <run> [--features <f.json>]` → gather evidence per query: **PREFER the Salesforce Docs MCP** (`salesforce_docs_search`/`fetch`) when connected — its official *.salesforce.com URLs pass R23 → `live_confirmed`; capture with `scripts/salesforce_docs_evidence.py` into `release-evidence-<lane>.json` (generic `web_search` is the fallback, same schema) → `release_crosswalk.py resolve --queries <q> --evidence <e> --lane A\|B --run-id <id> --output-dir <run> [--as-of Y-M-D]`. Live path primary; regex floor guarantees the legacy set; `--features` lets the SDD's own features drive verification. Scoring (binary): `in_force`=0; any confirmed-not-in-force (`retired`/`end_of_support`/`superseded`)=unified −3; `in_force_unverified`=−1 only if live ran (offline=0); cap −9/lane. Only a Salesforce URL (R23) asserts a status; successor sourced or "SA to confirm", never invented. `data/release-register.json` is the dated backstop (past `review_by` → REGISTER-STALE banner, surfaced only). Degrades live_confirmed/register_based/unverified. `release_awareness_check.py` = register-only back-compat shim. |
| 4a–4d (A) | five turns each: `pass_accumulate.py record --lane A\|B --dim-group 1-3\|4-7 --pass N --scores <p.json> --output-dir <run>`; then `pass_accumulate.py aggregate --lane A\|B --output-dir <run> --output <run>/lane-<L>-pass-aggregate.json`; merge into bundle (verbatim R16 attestation in every bundle) |
| R1–R2 (B) | model review (no script) → SDD-review bundle (`references/sdd-review-bundle-schema.md`) |
| 5 (A) | `score_sheet_populate.py --bundle <b.json> --blinding-label "Output A\|B" --run-record <rr.json> --output <sheet.xlsx> [--integration-heavy] [--blinding-extra-terms "..."]` — runs R1–R25; a failing bundle does not proceed |
| 6 (A) | `lift_calculate.py --output-a-score-sheet <a.xlsx> --output-b-score-sheet <b.xlsx> --output <lift.json>` — lift as a statistic (quote when its band excludes 0; "within noise" when it spans 0) |
| 7 (A) | First AUTHOR `{"exec_narrative":{what_we_evaluated,the_verdict,where_paid_off,where_trailed,release_currency,confidence_caveats,what_next}}` (grounded in THIS run's real dims/scores/mechanisms). Then `lane_reveal_apply.py --lane-mapping <esc> --lift-calc <lift.json> --run-record <rr.json> --zms-summary <sum.json> --release-awareness-a <ra-A.json> --release-awareness-b <ra-B.json> --exec-narrative <en.json> --output <diag.json>` — release-awareness + exec-narrative args required or §5.5/exec summary go thin |
| 8 (A) | `report_build_substantive.py --bundle <diag.json> --za-bundle <za.json> --ots-bundle <ots.json> --accuracy-gate <run>/accuracy-gate.json --output <report.docx>` — full Diagnostic Report; `--za/--ots-bundle` carry the content_coding the coverage matrix + IP-gap use. Deliverable is the .docx, never a chat summary |
| RB (B) | `sdd_review_validate.py` (mandatory gate: every finding grounded or honestly missing; every recommendation → a finding with what_to_change/why/what_good_looks_like/done_when; build_ready excludes unresolved blockers; no owner fields) → `report_build_sdd_review.py --bundle <b.json> --release <ra-A.json> --output <report.docx> [--top-n 8]` |

No em dashes in client-facing output. Report actions are ZenAgent-only; OTS is contrast, never its own action.

## Final output
**Mode A:** `diagnostic-report.docx` (branded, BLUF-led) + two score sheets + two content-mapping workbooks + crosswalk findings + lift + digest trail.
**Mode B:** `sdd-review-report.docx` (branded, BLUF-led): build-ready judgement, strengths/gaps by dimension-as-lens, top-N recommendations, release appendix + digest trail. No sheets/lift unless `--enable-single-scoring`.
