# TRD — W2 Evaluation Bench v2.0

Document 4 of 6 · Technical Requirements Document
(consumes: PRD, Application Flow, Backend Schema)

---

## 1. System architecture

```
Browser ──HTTPS──► Cloud Run service (single instance)
                   ├─ FastAPI (server/main.py)            no model client
                   ├─ Orchestrator FSM (orchestrator.py)  deterministic batches
                   ├─ Consensus engine (consensus.py)     v2.0 NEW, deterministic
                   ├─ Engine v4.7 (engine/evaluate-sdd + engine/zms, vendored)
                   ├─ Packet store (packets.py)           file-based
                   └─ /data ◄── GCS bucket volume mount   run state, escrow, reports
                          ▲
                          │ outbound HTTPS polling (X-W2-Token)
Runner daemon (operator machine/VM: runner/w2_runner.py)
  ├─ billing_guard.py  G1–G5
  ├─ Judge A (`claude-code`): `claude -p --output-format json` (subscription; scrubbed env)
  └─ Judge B (`gemini`): gemini_judge.py → generativelanguage.googleapis.com (GEMINI_API_KEY)
```

Trust boundaries: (1) the internet ↔ Cloud Run (token auth); (2) Cloud Run ↔
runner (token auth; runner initiates, never listens); (3) runner ↔ Anthropic
(subscription credential only, guarded); (4) runner ↔ Google (API key).
The Claude credential exists ONLY on the runner box. No credential of any
kind exists in the server image.

## 2. Technical requirements

### Server / deployment
- TR-1 Python 3.12; FastAPI + uvicorn; deps pinned in requirements.txt
  (fastapi, uvicorn, python-multipart, openpyxl, python-docx). No Anthropic or
  Google SDK in server/ — enforced by test T-9.
- TR-2 Container listens on `$PORT` (Cloud Run injects; default 8080).
  Stateless image; ALL mutable state under `$W2APP_DATA` (=/data, GCS volume).
- TR-3 Cloud Run config: `--max-instances 1` (single-writer file store),
  `--concurrency 40`, memory 1Gi, timeout 300s, `--allow-unauthenticated`
  with app-level `W2APP_TOKEN` middleware on `/api/*`. Deploy is
  `scripts/deploy_cloudrun.sh` (creates bucket, mounts volume, prints runner
  command).
- TR-4 `advance()` idempotency: every batch is a no-op when its output
  artifact exists; safe under Cloud Run restarts and duplicate packet POSTs.
- TR-5 GCS-FUSE semantics: no file locking, last-write-wins; acceptable
  because max-instances=1 and packet results are write-once (existence check
  before write). state.json writes are whole-file replaces.
- TR-6 The escrow file `.lane-mapping` MUST NOT be readable via any route:
  download whitelist only (Backend Schema §10), path traversal rejected in
  run_dir resolution, packet payload builders must not import or open it
  (enforced by test T-8).

### Runner
- TR-7 Daemon loop: poll `GET /api/packets/next` at `--poll` (default 3s);
  exponential backoff to 300s on connectivity errors; `--once` drains and
  exits (2 idle polls). Ships with systemd unit and optional Dockerfile.runner
  (credential injected at runtime, never baked).
- TR-8 Judge routing: `meta.judge` on pass/review packets; reconcile,
  narrative, exec_narrative, components, features, evidence → Judge A.
  NO silent fallback between judges (provenance integrity); a missing judge
  refuses at preflight.
- TR-9 Claude execution: `claude -p --output-format json`, prompt on stdin,
  `--allowed-tools ""` unless `needs_web`; scrubbed env (G1); JSON extracted
  fence-tolerantly; G4 cost assertion on every payload.
- TR-10 Gemini execution: REST `models/{GEMINI_MODEL}:generateContent`,
  `responseMimeType: application/json`, temperature 0.2; usageMetadata →
  ledger; model default `gemini-2.5-flash` overridable by env (pin a current
  Flash-class model at deploy time). Free-tier keys refused unless
  `W2_ALLOW_GEMINI_FREE_TIER=1` — detection: if a probe call returns free-tier
  quota headers/errors, refuse with the terms explanation (training/commercial
  restrictions).
- TR-11 Billing guards (unchanged, plus): G1 refuse+scrub
  ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN; G2 refuse apiKeyHelper/env
  injection in ~/.claude/settings.json and ./.claude/settings*.json;
  G3 key-free `claude -p` preflight; G4 nonzero `total_cost_usd` aborts;
  G5 per-packet usage ledger. `CLAUDE_CODE_OAUTH_TOKEN` is sanctioned and
  never scrubbed. Server tripwire: 402 + run error on any nonzero-cost
  result POST. These requirements are release-blocking.

### Multi-member operation (v2.0)
- TR-29 Per-member tokens (`W2APP_TOKENS`), owner stamping at run creation,
  owner-affinity claim rule, heartbeat ledger (in-memory + state file under
  $W2APP_DATA/runners.json). No roles; every member sees all runs (NG2).
- TR-30 `GET /install.sh`: templated POSIX installer served by the app;
  installs Claude Code (npm) if absent, invokes `claude setup-token`
  (browser flow on the member's machine; credential never transits the
  server), installs a launchd (macOS) / systemd --user (Linux/WSL) service,
  writes ~/.w2/env (0600), runs `w2_runner.py --selfcheck`, posts first
  heartbeat. Idempotent re-runs. Windows native = WSL path in the guide.
- TR-31 `w2_runner.py --selfcheck`: G1–G3 + Gemini preflight + server
  reachability + token validity, human-readable PASS/FAIL lines; exit code
  for the installer.

### Consensus engine (server/consensus.py — v2.0 core)
- TR-12 Pure functions, no I/O beyond the run dir; unit-testable:
  `diff(scorecard_a, scorecard_b, slice, thresholds) → divergences`,
  `merge(scorecards, rulings, contracts) → consensus_record`,
  `stats(consensus_record) → agreement_stats`. Thresholds and verdict order
  from contracts (SUB_DELTA_FRAC 0.20, DIM_DELTA_FRAC 0.10,
  Present>Partial>Absent).
- TR-13 Determinism: identical inputs → byte-identical consensus record
  (sorted keys, no timestamps inside the record body; timestamps live in
  state.json).
- TR-14 Conservative rule implementation: dissent verdict = weaker of the
  two; dissent score = min; Dim-3 RR netting and Dim-4 floor applied AFTER
  merge, to consensus values, using the lane's release summary and mapping
  floor from meta.
- TR-15 Reconcile packet construction: only divergent items; both judge
  entries verbatim; SDD embedded; blinded instructions; ruling schema
  enforced on result POST (shape check server-side; semantic checks in R26/27).

### Engine v4.7 revision (engine/evaluate-sdd)
- TR-16 contracts.py additions: JUDGES, SUB_DELTA_FRAC, DIM_DELTA_FRAC,
  VERDICT_ORDER, JUDGE_INDEPENDENCE_ATTESTATION, PROTOCOLS =
  {"dual-judge" (default), "five-pass"}. No existing constant changes.
- TR-17 `judge_accumulate.py` (new; pass_accumulate.py untouched for the
  legacy flag): persists scorecards, loads pairs, exposes
  `aggregate(lane, run_dir)` returning judge_runs_by_dimension +
  agreement_stats + modal-free consensus inputs.
- TR-18 score_sheet_populate.py: protocol switch — v4.7 path validates
  R1, R3–R28 as specified in Backend Schema §7 and fills Judge A / Judge B /
  Consensus columns; v4.6 path preserved verbatim behind the flag.
  Template: `Dim_1-7_Sub_Criteria` sheet columns Pass1..Pass5 → JudgeA,
  JudgeB, Consensus, Provenance.
- TR-19 lift_calculate.py: consensus totals headline; per-judge lifts;
  band = [min, max] of {lift_claude, lift_gemini, lift_consensus};
  agreement_overall forwarded. ICC/bootstrap machinery bypassed in dual-judge
  mode (n=2 judges — report the spread, don't model it).
- TR-20 report builders: provenance badges, agreement table, Dissent &
  Reconciliation annex (per dissent: criterion, both verdicts+anchors,
  ruling/why unresolved, conservative resolution), per-judge lift row,
  reliability label; Mode B: contested-recommendation styling. Brand styling
  via report_style.py unchanged (palette 1c4a4d / 139f94 / 22bcad / 8094c0 /
  059669 / c25008).

### Statistics
- TR-21 Agreement statistics exactly per Backend Schema §6.5; computed once
  in consensus.stats(), consumed by bundle, checkpoint, lift, and report —
  never recomputed independently (single-source rule).

### Performance & capacity
- TR-22 Token budget targets (20k-word docs): Claude ≤ 500k in / run Mode A;
  Gemini ≈ 212k in. Scoring packet ≈ 53k in (25k fixed overhead + 28k SDD);
  prompt assembly must keep fixed sections byte-stable across the 4 Claude
  scoring packets to maximize prompt-cache hits.
- TR-23 Wall-clock: Mode A ≤ ~30 min with a warm runner (8 scoring calls
  dominate; Claude and Gemini packets may be claimed concurrently by
  multiple runner processes — the protocol already supports N runners).
- TR-24 Upload limit 10 MB/file; text formats (md/txt; docx accepted and
  converted at intake if implemented in v2.1 — out of scope now, documents
  are md/txt).

### Security & privacy
- TR-25 Secrets: W2APP_TOKEN (Cloud Run env), CLAUDE_CODE_OAUTH_TOKEN +
  GEMINI_API_KEY (runner env / systemd override). Never logged; usage ledger
  contains counts only.
- TR-26 SDD/BRD content leaves the system only to Anthropic (subscription
  inference) and Google (Gemini API, paid tier = no training). State bucket
  is project-private; deliverables served only with the token.
- TR-27 Blinding: R14 scan extended to reconcile output; escrow rules TR-6.

### Observability
- TR-28 Per-run usage panel (packets, in/out tokens per judge, reported API
  cost line pinned at $0.00); state.json carries stage + error verbatim;
  uvicorn logs to Cloud Run logging; runner logs per-packet lines with judge
  + token counts.

## 3. Testing requirements

- T-1 Unit: consensus.diff/merge/stats — agreement, adopt-each-side,
  meet_between, dissent conservative rule, NA handling, Dim-3 netting,
  Dim-4 floor, determinism (double-run byte equality).
- T-2 Unit: divergence thresholds boundary cases (Δ exactly at 20%/10%).
- T-3 Unit: gemini_judge parse/usage against canned payloads (exists in v1.1,
  extend for error shapes and free-tier detection).
- T-4 Unit: R26/R27/R28 validator rules — passing and each failure mode.
- T-5 Mock dual-judge: mock_intelligence gains a judge parameter producing
  SEEDED DIVERGENCE (deterministic per packet_id: ~15% of criteria differ,
  including ≥1 forced dissent per run) so consensus, reconciliation, and the
  annex are exercised end-to-end without models.
- T-6 Smoke (scripts/smoke_e2e.sh): Mode A hands-free (assert done, report,
  dissents ≥1 rendered, agreement stats present, single-touch — no approve
  call needed), Mode A with pausing checkpoint (assert awaiting_checkpoint
  then approve), Mode B (assert build_ready + contested flags).
- T-7 Auth: 401/200/401 matrix + download token query param + member
  resolution from W2APP_TOKENS + affinity (member B's runner never receives
  member A's packets) + heartbeat surfacing.
- T-12 Installer: shellcheck clean; template rendering; idempotent re-run;
  selfcheck failure propagates nonzero exit.
- T-8 Escrow: request every route for `.lane-mapping` equivalents → 404;
  grep test: no server module outside lane_reveal_apply invocation path opens
  the escrow.
- T-9 Grep test: `anthropic` / `google` SDK imports absent from server/.
- T-10 Legacy: `EVAL_PROTOCOL=five-pass` smoke still green (v4.6 path frozen).
- T-11 Billing: server 402 on synthetic nonzero-cost result; runner G4 unit.

## 4. Migration from v1.1 (constraints on the build)

- The v1.1 packet protocol, storage layout, auth, guards, Cloud Run assets,
  and UI shell are the baseline; v2.0 must not break run directories created
  by v1.1 (old runs remain readable/downloadable; they simply predate
  consensus digests).
- pass_accumulate/five-pass code paths are frozen, not deleted.
- All new constants land in contracts.py first; no magic numbers in
  consensus.py, orchestrator, or reports (enforced in review).

## 5. Open technical risks

| Risk | Mitigation |
|---|---|
| Gemini model id drift / deprecations | GEMINI_MODEL env + preflight probe fails fast with actionable message |
| Gemini JSON discipline (schema drift in scorecards) | responseMimeType json + server-side shape validation on POST; malformed → packet stays open, logged |
| Judge scorecards diverge massively (agreement <0.5) | Not a failure: conservative consensus + prominent reliability label; report remains truthful |
| `claude -p` print-mode credit edge cases | G3/G4 tripwires make any billing regression loud and halting, never silent |
| GCS-FUSE latency on many small packet files | Acceptable at this scale (≤ ~25 files/run); batch reads in orchestrator where trivial |
| Prompt-cache misses inflating subscription draw | TR-22 byte-stable fixed sections; measure via ledger after first real run |
