# Implementation Plan — W2 Evaluation Bench v2.0

Document 6 of 6 · Build plan (consumes: all previous documents)
Baseline: unzip `w2-evaluation-bench-v1.1.zip` — a working five-pass
application with Cloud Run assets, guards, panel-mode runner, and green mock
smoke. This plan is written to be executed in Claude Code, phase by phase;
every phase ends at a runnable, testable state. Keep the mock smoke green at
every phase boundary.

---

## Phase 0 — Repo preparation (½ day)

0.1 Unzip baseline; `pip install -r requirements.txt`; run
    `bash scripts/smoke_e2e.sh` → must print SMOKE PASS (regression anchor).
0.2 Commit as `v1.1-baseline`. Add this document set under `docs/`.
0.3 Add `EVAL_PROTOCOL` env plumbing: config.py reads it
    (default `dual-judge`); thread into state.json as `protocol`.

Acceptance: smoke green; protocol field visible in a new run's state.

## Phase 1 — Engine v4.7 (contracts + consensus math + validators) (2–3 days)

1.1 `engine/evaluate-sdd/scripts/contracts.py`: add JUDGES,
    SUB_DELTA_FRAC=0.20, DIM_DELTA_FRAC=0.10, VERDICT_ORDER
    (Present>Partial>Absent), JUDGE_INDEPENDENCE_ATTESTATION (verbatim from
    Backend Schema §7), PROTOCOLS. Touch nothing existing.
1.2 New `server/consensus.py` (server-side module; engine-agnostic pure
    functions): `diff()`, `merge()`, `stats()` per Backend Schema §6.2–6.5
    and TRD TR-12–TR-14. Unit tests T-1/T-2 first (TDD here pays off — the
    conservative rule and threshold boundaries are the correctness core).
1.3 New `engine/evaluate-sdd/scripts/judge_accumulate.py`: persist
    scorecards to `scorecards/`, load pairs, `aggregate(lane, run_dir)` →
    judge_runs_by_dimension + inputs for consensus. Leave pass_accumulate.py
    untouched.
1.4 `score_sheet_populate.py`: add the v4.7 validation path (R2 retired;
    R3–R5 re-pointed at judge/consensus fields; R26/R27/R28 added per
    Backend Schema §7; R14 scan extended to ruling_rationale/citation; R25
    family applied to both judges' retained anchors and ruling citations).
    Protocol switch chooses v4.6 vs v4.7 path. Template columns: Pass1..5 →
    JudgeA/JudgeB/Consensus/Provenance on Dim_1-7_Sub_Criteria.
1.5 `lift_calculate.py`: consensus headline + judge_lifts + band; bypass
    bootstrap/ICC in dual-judge mode (TR-19).
1.6 Unit tests T-4 (each new rule: pass + every failure mode).

Acceptance: T-1/T-2/T-4 green; `EVAL_PROTOCOL=five-pass` legacy smoke green.

## Phase 2 — Server orchestration (2 days)

2.1 `orchestrator.stage_scoring_packets`: emit two byte-identical pass
    packets per lane×group with `meta.judge`; packet ids
    `pass:<label>:<group>:<judge>`.
2.2 New `orchestrator.batch_consensus`: persist scorecards
    (judge_accumulate) → consensus.diff → create `reconcile:<label>:<group>`
    packets for divergences (prompt builder 2.4) → on results,
    consensus.merge + stats → write `consensus/<lane>_<group>.json` +
    consensus digest into state.
2.3 `bundle_assemble.py`: v4.7 bundle per Backend Schema §7 —
    judge_runs_by_dimension, three-key sub entries + provenance,
    consensus_provenance, dissents, agreement fields,
    judge_independence_attestation from contracts, header.judge_models.
    Coding/citations built from CONSENSUS verdicts+anchors.
2.4 `prompts.py`: `reconcile_prompt()` (both judge entries verbatim + SDD +
    ruling schema + blinding instructions); pass/narrative prompts updated to
    reference consensus digests; keep fixed sections byte-stable across
    packets (TR-22 cache alignment).
2.5 Checkpoint: panel gains agreement_rate + dissent_count;
    auto_approve default true at POST /api/runs (main.py form default).
2.6a Multi-member (TR-29): W2APP_TOKENS parsing, owner stamping, affinity
    in /api/packets/next, heartbeat ledger + GET /api/runners. Tests in T-7.
2.6 `batch_reveal_and_report` digests: judge_lifts, lift_band,
    agreement_overall (Backend Schema §9).
2.7 Mode B: review packets ×2 judges (`review:<group>:<judge>`); consensus on
    findings keyed by zms_lens; `reconcile:review` packet on divergent
    verdicts; contested flags; bundle deltas per Backend Schema §11;
    extend sdd_review_validate accordingly.

Acceptance: with mock runner (Phase 3), a Mode A run reaches error at bundle
validation or passes — drive iteratively against the R-rules until done.

## Phase 3 — Runner & mock (1–1½ days)

3.1 `w2_runner.py`: route by `meta.judge` (panel is now the DEFAULT engine;
    `--engine claude-code` remains for single-judge legacy protocol runs);
    handle `reconcile` kind (Judge A). Remove --gemini-passes (obsolete).
3.2 `gemini_judge.py`: free-tier detection + refusal (TR-10); error shapes
    → packet stays open with logged reason.
3.3 `mock_intelligence.py`: judge-aware execution — deterministic seeded
    divergence (~15% of criteria per packet differ by judge; ≥1 forced
    dissent per run: a criterion where the reconcile mock returns `dissent`);
    `reconcile` handler returns evidence-cited rulings (reuse the anchor
    machinery — citations must survive R25). This is T-5 and the engine of
    the whole test strategy.
3.4 Tests T-3 (gemini payloads), T-11 (billing 402 + G4).

Acceptance: full mock Mode A hands-free run → done; dissents ≥1 in bundle.

## Phase 4 — Reports (1–1½ days)

4.1 `report_build_substantive.py`: agreement table (per-dim concordance +
    verdict agreement + reliability label), judge provenance badges on
    dimension assessments, per-judge lift row + band in §1, Dissent &
    Reconciliation annex (per dissent: criterion, both verdicts + anchors,
    why unresolved, conservative resolution), exec-narrative fields for
    concurrence.
4.2 `report_build_sdd_review.py`: judge provenance on findings; contested
    styling on dissent-derived recommendations; agreement summary block.
4.3 Visual QA against report_style.py brand rules; verify anchors render
    verbatim.

Acceptance: sample .docx from mock runs show annex with the forced dissent;
all provenance badges populated.

## Phase 5 — Console UI (1 day)

5.1 Stage rail: insert `consensus` stage; hands-free default in the form;
    judging badge (fixed panel label).
5.2 Judging panel: concurrence meter (SVG, two tracks fusing per dimension,
    dissent dots), stat chips, table-equivalent toggle (UI/UX Brief §3.4, §6).
5.3 Usage line split per judge; checkpoint panel read-only auto-approved
    variant; revealed-result judge lifts + annex pointer; runner-offline
    banner; tripwire error copy.

Acceptance: manual pass over UI/UX Brief §3–§6 checklist at 1280px and 380px.

## Phase 6 — Integration, deploy, docs (1 day)

6.1 `scripts/smoke_e2e.sh` v2: Mode A hands-free (assert done WITHOUT any
    approve call, dissents ≥1, agreement stats present), Mode A paused
    (assert awaiting_checkpoint → approve → done), Mode B (contested flags),
    legacy `EVAL_PROTOCOL=five-pass` run (T-10), auth matrix (T-7), escrow +
    SDK grep tests (T-8/T-9).
6.2 Cloud Run shakedown: deploy to a test project; one real dual-judge run
    with small documents; verify usage ledger, $0.00 line, GCS persistence
    across a forced instance restart, Gemini paid-tier path.
6.3 Installer + guide (TR-30/31): `server/install_template.sh`, GET
    /install.sh route, `--selfcheck` in the runner, launchd plist + systemd
    --user unit templates; verify docs/07-installation-guide.md steps
    verbatim on macOS and Linux; T-12.
6.4 README + in-app runner card copy updated to v2.0; CHANGELOG; tag v2.0.

Release gate: PRD §10 criteria; TRD §3 test suite green; SM-1..SM-5 verified
on the shakedown run.

## Sequencing summary

```
P0 baseline ─ P1 engine math+rules ─ P2 orchestration ─ P3 runner/mock ─┐
                                                                        ├─ P4 reports ─ P5 UI ─ P6 integrate+deploy
                    (P2 and P3 iterate together against R1–R28)  ───────┘
```
Estimated effort: 9–11 working days single engineer with Claude Code
(multi-member + installer adds ~1 day).

## Risk register (build-time)

| # | Risk | Mitigation |
|---|---|---|
| R-1 | R-rule whack-a-mole during P2/P3 (as in v1.x) | Drive with `--validate-bundle-only`; fix mock/assembler against the verbatim rule text; budget the iteration — it is the QA working |
| R-2 | Consensus math edge cases (NA, all-dissent, empty group) | T-1 covers each explicitly before orchestration wiring |
| R-3 | Gemini scorecard schema drift | Server-side shape validation on POST; malformed leaves packet open with reason |
| R-4 | Scope creep into 3-judge / operator arbitration | Locked out by PRD decision log D1/D4 — cite it in review |
| R-5 | Legacy path rot | T-10 in smoke keeps five-pass frozen-green |
| R-6 | Real-run token overrun vs budget | Ledger comparison after shakedown; tune digest caps before adjusting scope |

## Decision references

All build-time judgment calls defer to PRD §7 (decision log D1–D12). If a
conflict between documents is found during the build: Backend Schema wins on
data shapes, Application Flow on behavior, PRD on scope — and the conflict
gets recorded as an erratum in docs/.
