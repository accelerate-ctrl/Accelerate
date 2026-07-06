# Backend Schema — W2 Evaluation Bench v2.0

Document 3 of 6 · Data model specification (consumes: PRD, Application Flow)
The store is **file-based** (one directory per run on the GCS-mounted volume);
"schema" below means directory layout + JSON contracts + validation rules +
HTTP API shapes. Engine constants cited here are the verbatim single source of
truth in `engine/evaluate-sdd/scripts/contracts.py` (v4.7).

---

## 1. Storage layout

```
$W2APP_DATA/                      # Cloud Run: /data (GCS volume); local: ./data
└── runs/<run_id>/                # run_id = W2-<YYYYMMDD-HHMMSS>-<A|B>-<hex6>
    ├── state.json                # orchestrator state (§2)
    ├── inputs/                   # uploaded files, verbatim
    ├── .lane-mapping             # ESCROW: label↔identity. Never served, never
    │                             # read by packet builders; first read at reveal
    ├── section-a-output.json     # intake digest (hashes, flags, lane_files)
    ├── run-record.json           # provenance record
    ├── zms-calibration-{content,summary}.json
    ├── zms-calibration-dims-{1-3,4-7}.json
    ├── components-{a,b}.json  features-{A,B}.json
    ├── section-c-output-{a,b}.json   content-mapping.xlsx
    ├── release-queries-{A,B}.json  release-evidence-{A,B}.json
    ├── release-awareness-{A,B}.json
    ├── packets/<pid>.packet.json / <pid>.result.json     (§4)
    ├── scorecards/<lane>_<group>_<judge>.json            (§5, v2.0 NEW)
    ├── consensus/<lane>_<group>.json                     (§6, v2.0 NEW)
    ├── output-{a,b}-scoring-bundle.json                  (§7)
    ├── sdd-index-{a,b}.json
    ├── output-{a,b}-score-sheet.xlsx
    ├── lift-calc.json  exec-narrative.json
    ├── diagnostic-bundle.json  diagnostic-report.docx    (Mode A)
    └── sdd-review-bundle.json  sdd-review-report.docx    (Mode B)
```

## 2. `state.json`

```jsonc
{
  "run_id": "W2-20260703-101500-A-ab12cd",
  "mode": "A" | "B",
  "status": "created|running|awaiting_packets|awaiting_checkpoint|stopped|error|done",
  "stage": "S0|S1|S2|S3|S3.5|S4|S5",
  "created_at": "…", "updated_at": "…",
  "files": {"brd": "...", "sdd_1": "...", "sdd_2?": "..."},
  "owner": "alice",                         // v2.0: member id from the presenting token
  "zenagent_is": "a" | "b",                 // Mode A; consumed only by intake→escrow
  "live_evidence": false,
  "auto_approve_checkpoint": true,          // v2.0 DEFAULT true
  "evaluator_model": "panel:claude-code+gemini",
  "protocol": "dual-judge",                 // v2.0; "five-pass" only via env flag
  "lane_files": {"Output A": "<path>", "Output B": "<path>"},
  "digests": {
    "intake":   {run_id, run_type, applicability_flags, integration_count,
                 run_integration_heavy, lane_files},
    "zms":      {zms_version, applicable_criteria_count},
    "mapping":  {"<label>": {stub_missing_count_over_8_required, dim_4_floor_cap}},
    "release":  {"<label>": <summary>},
    "consensus":{"<label>": {verdict_agreement_rate, score_concordance,
                 divergences, dissents}},                       // v2.0 NEW
    "sheets":   {"<label>": {final_score, computed{…}}},
    "reveal":   {headline_lift_za_minus_ots, za_total, ots_total,
                 judge_lifts: {claude, gemini}, lift_band: [lo, hi],   // v2.0
                 za_label, agreement_overall},
    "review":   {build_ready, findings, recommendations, dissents}   // Mode B
  },
  "checkpoint": { …blinded panel, §8… },
  "checkpoint_approved": true,
  "checkpoint_approved_at": "…",
  "checkpoint_approved_by": "auto (pre-authorized at intake)" | "operator",
  "error": null | "<message incl. verbatim failing rule>",
  "traceback": "<tail, error only>"
}
```

## 3. Engine constants (contracts.py — verbatim values, v4.7 unchanged where listed)

- `DIM_MAX` (normal, integration_heavy): 1:(15,15) 2:(15,15) 3:(20,20)
  4:(15,15) 5:(10,15) 6:(10,10) 7:(15,10). Integration-heavy swap: Dim-5
  10→15, Dim-7 15→10; flag from run-record.
- Bands `BAND_SCALE`: ≥80% STRONG, ≥70% GOOD, ≥65% ADEQUATE, else WEAK.
  `GATE_TO_BAND`: PASS→STRONG, MARGINAL_PASS→GOOD, MARGINAL_FAIL→ADEQUATE,
  FAIL→WEAK.
- Dim-4 floor caps: 0 missing/stub → no cap; 1–2 → cap 10; ≥3 → cap 7.
- RR deductions: confirmed not-in-force −3; in-force-unverified (live path
  only) −1; cumulative cap −9. Register path never penalises unverified.
- Attestations: `BLINDING_ATTESTATION`, `NON_BIAS_ATTESTATION`, and (v4.7 NEW)
  `JUDGE_INDEPENDENCE_ATTESTATION` — enforced character-for-character.
- v4.7 NEW: `JUDGES = ("claude-code", "gemini")`; divergence thresholds
  `SUB_DELTA_FRAC = 0.20`, `DIM_DELTA_FRAC = 0.10`; verdict order for the
  conservative rule `Present > Partial > Absent` (NA excluded from consensus
  arithmetic).

Sub-criterion structure (bundle §7 keys, maxima):
Dim1 requirement_parsing_depth/stakeholder_persona_recognition/
constraint_assumption_extraction 5/5/5 · Dim2 functional_requirement_
traceability/nfr_coverage/gap_risk_identification 5/5/5 · Dim3
cloud_module_selection/trusted_design/easy_design/adaptable_design 5/5/5/5
(+ multi_cloud_architecture 5 when applicable) · Dim4 component_presence 9,
architectural_decision_quality 6 (+ floor_cap, raw_sum_before_floor,
final_dim_4_score) · Dim5 4/3/3 · Dim6 4/3/3 · Dim7 5/5/5.

## 4. Packet store

`packets/<sanitized-pid>.packet.json`:
```jsonc
{"packet_id": "pass:Output A:1-3:gemini", "kind": "components|features|evidence|
  pass|reconcile|review|narrative|exec_narrative",
 "label": "Output A|Output B|run", "prompt": "<self-contained>",
 "meta": {"lane": "A", "dim_group": "1-3", "judge": "claude-code|gemini",
          "floor_cap": 10, "rr_capped_total": -9},   // pass/reconcile kinds
 "needs_web": false, "schema_hint": {…}|null,
 "created_at": "…", "claimed_by": null|"runner-…", "claimed_at": null|"…"}
```
`<pid>.result.json`: `{"result": {…}, "usage": {input_tokens, output_tokens,
judge, model, engine, total_cost_usd}, "completed_at": "…"}`.
Claim rule: unclaimed, same runner, or claim older than 90s. Duplicate result
writes are ignored. Usage totals aggregate per run; any nonzero
`total_cost_usd` on POST → HTTP 402 + run error (server tripwire).

## 5. Scorecard schema (`pass` result; one per judge) — v2.0

```jsonc
{"dim_scores": {"1": 11.5, "2": …},              // only this packet's dim-group
 "sub_scores": {"1": {"requirement_parsing_depth": 3.9, …}, …},
 "verdicts": {"<zms_criterion_id>": {
    "verdict": "Present|Partial|Absent|NA",
    "evidence_anchor": "<VERBATIM SDD substring ≤25 words; Absent → 'topic absent from SDD'>",
    "sdd_ref": "…",
    "components_present": [], "components_partial": [], "components_absent": []}}}
```
Persisted verbatim to `scorecards/<lane>_<group>_<judge>.json` at consensus
start (audit trail independent of packet retention).

## 6. Consensus record (`consensus/<lane>_<group>.json`) — v2.0

### 6.1 shape
```jsonc
{"lane": "A", "dim_group": "1-3",
 "judges": {"claude-code": "<scorecard ref>", "gemini": "<scorecard ref>"},
 "items": {"<zms_criterion_id>": {
    "provenance": "agreed|adopt_claude|adopt_gemini|meet_between|dissent",
    "consensus": {verdict, evidence_anchor, sdd_ref, components_*},
    "judge_entries": {"claude-code": {…}, "gemini": {…}},   // divergent items
    "ruling_citation": "<verbatim SDD quote>"|null,
    "ruling_rationale": "<1–2 sentences>"|null }},
 "sub_scores": {"<dim>": {"<sub_key>": {"claude-code": x, "gemini": y,
                "consensus": z, "provenance": "…"}}},
 "dim_scores": {"<dim>": {"claude-code": x, "gemini": y, "consensus": z}},
 "dissents": [{"criterion_id"|"sub_key"|"dim": …,
    "claude-code": {…}, "gemini": {…},
    "conservative_resolution": {…},
    "why_unresolved": "<from reconcile ruling>"}],
 "stats": {…, §6.5}}
```

### 6.2 merge algorithm (deterministic, server-side)
1. Criterion level: identical verdicts → agreed (Judge A's anchor kept; both
   retained in judge_entries when texts differ). Divergent → reconcile ruling
   applied; `dissent` → conservative verdict (weaker per D-order), anchor from
   the judge whose verdict was kept; record appended to `dissents`.
2. Sub-scores: if |Δ| ≤ 20% of sub max → consensus = mean, provenance agreed.
   Else ruling (adopt/meet with cause) or dissent → `min(a, b)`.
3. Dim scores: recomputed as Σ consensus sub-scores; Dim-3 net of the lane's
   RR capped total (floor 0); Dim-4 `min(raw, floor_cap)`; then the 10%-of-max
   dim check is re-asserted (divergence here after sub-merge is impossible by
   construction; assert defensively).
4. NA verdicts participate in neither coverage nor agreement denominators.

### 6.3 divergence definition (creates reconcile items)
verdict mismatch · Present/Partial anchor pairs with zero shared
content-word (>3 chars, whitespace-collapsed, punctuation kept — the
evidence_anchor_verify tokenization) · |sub Δ| > 0.20 × sub_max ·
|dim Δ| > 0.10 × dim_max.

### 6.4 reconcile packet result schema
```jsonc
{"rulings": {"<item_key>": {"ruling": "adopt_claude|adopt_gemini|meet_between|dissent",
   "value": {…consensus entry or score…}|null,       // required unless dissent
   "citation": "<verbatim SDD substring>",           // required unless dissent
   "rationale": "<1–2 sentences, blinded>"}}}
```

### 6.5 agreement statistics (replaces five-pass stddev/ICC)
- `verdict_agreement_rate` = matched verdicts / non-NA criteria (per dim + overall)
- `score_concordance` per dim = 1 − |dimA − dimB| / dim_max; overall = weighted mean
- `divergence_count`, `dissent_count` (criterion/sub/dim granularity)
- `agreement_overall` = 0.5·verdict_agreement_rate + 0.5·score_concordance
- reliability label thresholds: ≥0.85 "strong cross-model concurrence";
  0.70–0.85 "moderate — read the annex"; <0.70 "weak — treat scores as contested"

## 7. Scoring bundle v4.7 (per lane; validated by R1–R28)

Changes from v4.6 (everything not listed is carried forward verbatim,
including content_coding, zms_calibration_citations, deductions,
per_dim_truth_source, release_awareness_findings with `source_url` on the
Salesforce domain whitelist):

- REPLACED `five_runs_by_dimension` → `judge_runs_by_dimension`:
  `{"claude-code": {"1": x,…,"7": x}, "gemini": {…}, "consensus": {…}}`
- REPLACED `per_dim_stddev`/`per_dim_variance_flag` → `per_dim_agreement`
  (score_concordance per dim) and `agreement_stats` (§6.5 object)
- Sub-criteria entries: `scores` → three-key object
  `{"claude-code": x, "gemini": y, "consensus": z}` + `provenance`
- NEW top-level `consensus_provenance`: criterion_id → provenance string
- NEW top-level `dissents` (copied from §6.1, both lanes' groups merged)
- NEW `judge_independence_attestation` (verbatim from contracts):
  "I confirm that each judge scored this SDD independently from an identical
  blinded packet, that neither judge's output was available to the other
  before reconciliation, and that every consensus value traces to an agreed
  verdict, an evidence-cited ruling, or a recorded dissent resolved
  conservatively."
- `header.evaluator_model` = "panel:claude-code+gemini";
  `header.judge_models` = {"claude-code": "<model_version>", "gemini": "<model>"}

### Validation rules
R1 label · R3/R4 recomputed means→ now consensus totals recomputation ·
R5 → agreement fields consistent with judge values · R6 bands · R7
truth-source verbatim · R8/R8c sub structure (three-key objects, all subs) ·
R9 dim-4 floor consistency · R10 deduction shape/values · R11 firewall
phrasings · R12 citation fields · R13 reasoning↔citation overlap ·
R14 blinding-leak scan (now ALSO over ruling_rationale/ruling_citation) ·
R15/R16 attestations verbatim · R17 required top-level fields (v4.7 set) ·
R18 BRD refs dims 1/2/6 · R19 coverage exhaustiveness · R20 anchors on
Partial/Absent Zennify criteria · R21/R22/R23/R24 deduction↔finding↔source
chain (`source_url` on *.salesforce.com) · R25/b/c/e anchor groundedness,
index resolution, negative_evidence on Absent, criterion relevance —
applied to BOTH judges' retained anchors and every ruling_citation ·
**R26 (NEW)** every applicable criterion has consensus_provenance and every
non-`agreed` provenance has judge_entries + (citation or dissent) ·
**R27 (NEW)** dissent integrity: every dissent's conservative_resolution is
the weaker/lower of the two judge values, and every `dissent` ruling appears
exactly once in `dissents` · **R28 (NEW)** judge_independence_attestation
verbatim; `judge_runs_by_dimension` contains exactly the two configured
judges + consensus.

R2 (five-numeric arrays) is retired in dual-judge protocol; under
`EVAL_PROTOCOL=five-pass` the v4.6 validator path is used unchanged.

## 8. Checkpoint panel (blinded)

```jsonc
{"zms": {zms_version, zms_frozen_at, applicable_criteria_count, criteria_by_source},
 "lanes": {"<label>": {total, per_dim_mean, agreement_rate, dissent_count,
   trust_deductions, rr_deductions,
   mapping: {stub_missing_count_over_8_required, dim_4_floor_cap},
   release_summary: {findings_total, by_status, rr_deductions_capped_total}}}}
```

## 9. Lift & reveal artifacts

`lift-calc.json`: computed on **consensus** lane totals with the v4.6
integration-heavy weight handling; PLUS `judge_lifts` = the same computation
on each judge's totals. `diagnostic-bundle.json` section_1 gains:
`judge_lifts {claude-code, gemini}`, `lift_band [min, max] of the three`,
`agreement_overall`; `lift_uncertainty` narrative: "band spans the two
judges' independent reads; a lift whose sign holds across both model families
is directionally robust."

## 10. HTTP API (complete)

| Method & path | Auth | Body / params | Returns |
|---|---|---|---|
| POST /api/runs | X-W2-Token | multipart: brd, sdd_1, [sdd_2], zenagent_is=a\|b, live_evidence, auto_approve_checkpoint (default true), evaluator_model | {run_id, mode, status} |
| GET /api/runs | token | — | [{run_id, mode, status, stage, created/updated, error, usage}] |
| GET /api/runs/{id} | token | — | state (escrow-free) + open_packets + usage + artifacts |
| POST /api/runs/{id}/approve | token | {approve: bool, reason?} | new state (409 unless awaiting_checkpoint) |
| GET /api/runs/{id}/download/{key} | token (header or ?token=) | key ∈ report, score_sheet_a/b, content_mapping, release_a/b, lift, run_record, diagnostic_bundle | file |
| GET /api/packets/next | token | runner_id | packet+run_id or {packet_id: null} |
| POST /api/packets/{run}/{pid}/result | token | {result, usage} | {status, stage}; 402 on nonzero cost; 404 unknown pid |

Auth (v2.0): `W2APP_TOKENS="alice:tokA,bob:tokB"` maps member→token
(single-token `W2APP_TOKEN` still honored as member "operator"). Middleware on
`/api/*` resolves the presenting token to a member id; 401 otherwise. Static
surfaces exempt.

Additional routes:

| Method & path | Auth | Purpose |
|---|---|---|
| GET /install.sh?token=… | member token | Personalized installer script (server URL + token templated in; never logs the token) |
| GET /api/runners | member token | Heartbeats: [{member, runner_id, last_seen, engine}] — powers "your runner: connected" |

Affinity rule: `GET /api/packets/next` releases packets only from runs whose
`owner` equals the presenting member; each call updates that member's
heartbeat. `POST /api/runs` stamps `owner` from the presenting token.

## 11. Mode B bundle deltas

`sdd-review-bundle.json` (validated by sdd_review_validate, extended):
findings gain `judge_provenance` ∈ {agreed, adopt_*, dissent} and optional
`judge_entries`; new top-level `dissents`; recommendations REC_REQUIRED
fields unchanged (what_to_change / why_it_matters / what_good_looks_like /
done_when); dissent-derived recommendations carry `contested: true`. Statuses
remain SA_CONFIRMATION_REQUIRED / CLIENT_CLARIFICATION_REQUIRED /
ORG_CONTEXT_REQUIRED / LICENSE_CONFIRMATION_REQUIRED / NOT_ASSESSABLE; no
owner fields.
