# Errata & Build Decisions — v2.0 build

Recorded per 06-implementation-plan.md "Decision references": conflicts found
during the build are recorded here, resolved by the precedence rule (Backend
Schema wins on data shapes, Application Flow on behavior, PRD on scope) or by
explicit operator sign-off. All items below were approved by the operator
before Phase 0 began.

## Document errata (stale cross-references)

- E-1. 00-INDEX.md and 06-implementation-plan.md cite "D1–D12", "T-1..11",
  "TR-1..28". The authoritative counts are the detailed documents' own:
  **D1–D14** (01-PRD §7), **T-1..T-12** (04-TRD §3), **TR-1..TR-31** (04-TRD §2).
- E-2. 02-application-flow.md / 06-implementation-plan.md show the installer
  invoked as `install.sh | bash -s -- --token <t>`; 03-backend-schema.md §10
  and 07-installation-guide.md show `GET /install.sh?token=…`. **Resolution
  (operator-approved, security override of schema precedence):** the
  bash-argument form is canonical in the guide (a token in a URL query string
  lands in Cloud Run request logs, outside the app's control); the `?token=`
  query form remains supported for convenience and its exposure is documented.
- E-3. 05-ui-ux-brief §8 footer says "six-document build set": read as the
  governing spec set 01–06 (00 is an index, 07 the per-member handout).
- E-4. "28-rule validation" is the nominal R1–R28 catalogue; R2 is retired in
  dual-judge mode (active set R1, R3–R28) and lives on under
  `EVAL_PROTOCOL=five-pass`.

## Prototype corrections (doc 05 wins; operator informed)

- P-1. The prototype's Google "Sign in" modal is demo-only. Built per doc 05
  §3.5 / PRD D14: minimal token prompt, localStorage, no account UI.
- P-2. The prototype's DIM_META dimension names (dims 5–7 "Security & trust",
  "Operations & reliability", "Integration & data") are demo data. Built with
  the engine's dimensions: 1 BRD Comprehension, 2 Requirement Coverage,
  3 Salesforce Solution Fit, 4 Design Specificity, 5 Dependencies and
  Assumptions, 6 Scope Discipline, 7 Estimation Readiness.
- P-3 (adopted). The prototype's Mode B stage rail
  `intake → setup → mapping → dual scoring → consensus → review+report` is
  adopted (doc 05 specifies only the Mode A rail).

## Underspecified points — operator-approved resolutions

- Q2. §6.5 "weighted mean" for overall score_concordance: weighted by
  dim_max. Run-level agreement_overall (reveal digest): mean of the two
  lanes' overalls weighted by non-NA applicable-criteria count.
- Q3. Gemini free-tier detection is best-effort and FAIL-CLOSED; override
  `W2_ALLOW_GEMINI_FREE_TIER=1` (PRD D8). Heuristic finalized at the Phase 6
  shakedown against the live API.
- Q4. Mode B consensus: findings matched by zms_lens; matched-different AND
  one-sided findings all go to the single `reconcile:review` packet;
  conservative order for finding-verdict dissents is risk > gap > strength
  (the more critical claim survives); is_blocking=true wins; `requires`
  statuses union. Mode B has no scores, so agreement_overall =
  verdict_agreement_rate alone, labelled as such.
- Q6. Five-pass variance-flag consumers (OH §3.9 derivations: priority review
  "Variance" items; Estimation Handoff Ready→Conditional on Dim-7 flag) map to
  the dual-judge instability signal: a dimension is flagged iff any recorded
  dissent touches it (criterion, sub, or dim level).
- Q7. Bundle placement of divergent judge material: content_coding
  zms_components entries carry `provenance` and, when provenance != agreed,
  `judge_entries`; top-level `consensus_provenance` remains the flat
  criterion→provenance map (Backend Schema §7). R26 validates both.
- Q8. Reconcile item keys: criterion items use the bare zms_criterion_id;
  sub-score items use `sub:<dim>:<sub_key>`. Dimension-level divergence is
  asserted, never judge-ruled (Backend Schema §6.2.3).
- Q9. Five-pass protocol: retired from every live path and from the UI;
  retained frozen behind `EVAL_PROTOCOL=five-pass` for regression (PRD D6,
  TRD §4). Not deleted.
- Q10. Mode A (blinded two-SDD comparison with methodology lift) remains in
  scope per PRD; reports in BOTH modes are structured refinement-first
  (operator direction), ADDITIVELY: no v1.1/v4.6 report section, table,
  anchor or traceability element is removed or reduced.

## Additional v1.1-code-vs-docs gaps closed in this build

- V-1. v1.1 `packets.complete` overwrote on duplicate result POST; Flow §8 /
  TR-5 require write-once. Guard added in v2.0.
- V-2. v1.1 `lift_calculate` reads five-pass arrays by screen-scraping the
  populated XLSX (Variance_Record C–G, exactly 5 numerics required). v4.7 adds
  a bundle-input dual-judge path; the XLSX becomes presentation-only. v4.6
  scrape path preserved behind the protocol flag.
- V-3. The five-pass shape lives in FOUR template surfaces (Dim_1-7 pass
  columns + Mean formula, Variance_Record matrices, Cover R1–R25 checklist,
  sheet header prose), not just the one named in TR-18. A v4.7 template asset
  is authored; the v4.6 template is untouched for the legacy flag.
- V-4. `examples/w2-runner.service` is a system-level unit; TR-30 requires
  user-level. v2.0 ships a `systemd --user` unit and the launchd plist that
  07-installation-guide references (new files).
- V-5. `Dockerfile.runner` default engine `claude-code` → `panel` in v2.0.
