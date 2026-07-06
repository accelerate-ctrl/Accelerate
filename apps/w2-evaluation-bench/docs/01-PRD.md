# PRD — W2 Evaluation Bench v2.0 (Dual-Judge Consensus)

Document 1 of 6 · Product Requirements Document
Consumers: TRD, Application Flow, UI/UX Brief, Backend Schema, Implementation Plan
Baseline codebase: `w2-evaluation-bench-v1.1.zip` (working five-pass application)
Engine baseline: Solutioning Evaluation Framework v4.6 → revised to **v4.7** by this build

---

## 1. Product summary

W2 Evaluation Bench is Zennify's self-hosted web application for the
Solutioning Evaluation Framework (Workflow 2). An operator uploads a BRD plus
two SDDs (Mode A, blinded comparative evaluation producing the ZennAgent
methodology lift) or a BRD plus one SDD (Mode B, qualitative review). The
application runs the pipeline end to end and delivers the branded Diagnostic
Report / SDD Review Report plus the full audit trail.

v2.0 replaces the engine's five-repetition scoring protocol with a
**dual-judge consensus protocol**: every scoring unit is judged independently
by two model families — Claude (via Claude Code, operator's subscription) and
Gemini (via the Gemini API) — from identical blinded packets. Divergences are
reconciled against document evidence; unresolvable conflicts are preserved as
dissents and resolved conservatively. The report presents an assessment that
has demonstrably survived scrutiny by two unrelated models.

## 2. Users and context

Personas: **two to five Zennify evaluating members** on the organization's
Claude Team plan (each with a premium seat), running evaluations **per deal —
typically weekly, not daily**. Each member self-installs a personal runner on
their own laptop (one guided setup), then interacts once per evaluation. Secondary
readers: recipients of the generated reports (practice leads, clients) — they
never touch the application.

Deployment context: the application (frontend + deterministic pipeline) runs
on Google Cloud Run; the intelligence layer (Claude Code) runs as a background
daemon on operator-controlled compute, polling the application over HTTPS.
Gemini participates via API key. See TRD §2.

## 3. Problem and rationale for v2.0

The v1.1 five-pass protocol measured within-model consistency (the same judge
reading the same SDD five times). Its own ICC statistics demonstrated the
weakness: passes correlate at ρ̂ ≈ 0.97, so five passes carry ~1 effective
measurement. It also cost ~1.1M subscription input tokens per Mode A run.
Dual-judge consensus measures **cross-model concurrence** — agreement between
two independently trained model families — which is a stronger reliability
claim, produces a richer report (agreement statistics + dissent annex), and
cuts subscription token draw by roughly 60%.

## 4. Goals / non-goals

Goals (v2.0):
- G1. One operator touchpoint per run (upload). Everything else automatic.
- G2. Every scoring unit judged independently by exactly two judges (Claude,
  Gemini) from byte-identical blinded packets.
- G3. Deterministic, evidence-ruled consensus with preserved dissents; nothing
  silently averaged.
- G4. Reports enriched with dual-judge provenance, per-dimension agreement
  statistics, and a Dissent & Reconciliation annex.
- G5. Zero Anthropic API spend — subscription tokens only (guards G1–G5 +
  server tripwire carried forward unchanged).
- G6. Cloud Run deployment with persistent run state; runner as an installed
  background daemon.

Non-goals (v2.0):
- NG1. More than two judges, or judge marketplaces.
- NG2. Full multi-tenant RBAC. (Per-member access tokens and owner-pays
  runner affinity ARE in scope — see FR-13; roles/permissions are not.)
- NG3. Real-time streaming of judge output to the UI.
- NG4. Automated SDD generation (Workflow 1) or Library benchmarking.
- NG5. Retaining the five-pass protocol as a first-class mode. It survives
  only as a frozen engine flag (`EVAL_PROTOCOL=five-pass`) for regression
  comparison, not exposed in the UI.

## 5. Functional requirements

FR-1 **Upload & mode detection.** Multipart upload: `brd` + `sdd_1`
(+ `sdd_2`) → Mode A; without `sdd_2` → Mode B. Mode A requires the ZenAgent
lane declaration (`zenagent_is` ∈ {a, b}), sealed into the escrow at intake.
Options at upload: live release evidence (default off), pausing D.5 checkpoint
(default off — hands-free is the default in v2.0), judging label (fixed
`panel:claude-code+gemini` in v2.0).

FR-2 **One-touch operation.** After upload, the run proceeds without operator
input through intake, ZMS load, mapping, crosswalk, dual-judge scoring,
consensus, checkpoint (auto-approved, panel recorded), sheets, lift, reveal,
and report. The only per-run operator action besides upload is optional:
downloading deliverables (a zero-decision act) or stopping a paused checkpoint
if the pausing option was chosen.

FR-3 **Dual-judge scoring.** Per lane × dimension-group (1–3, 4–7), the server
issues two `pass` packets differing only in `meta.judge` ∈ {claude-code,
gemini}. The runner routes each to its judge. Packets are byte-identical in
`prompt`. Each judge returns a full scorecard (dim scores, sub scores,
per-criterion verdicts with verbatim evidence anchors). Neither judge ever
sees the other's output at this stage.

FR-4 **Consensus & reconciliation.** The server deterministically diffs the two
scorecards. Agreements pass through with provenance `agreed`. Divergences
(defined in Backend Schema §6.3) are batched into one `reconcile` packet per
lane × dim-group, executed by Claude Code (still blinded), which must rule per
item by citing the SDD: adopt one judge, meet between with stated cause, or
declare `dissent`. Dissents resolve conservatively (weaker verdict / lower
score) and are preserved verbatim in the bundle and report. Reconciliation
never escalates to the operator.

FR-5 **Consensus bundle & validation.** The consensus scorecard, both judge
scorecards, provenance per criterion, agreement statistics, and dissents are
assembled into the v4.7 bundle and validated by the revised rule set
(R1–R28; see Backend Schema §7). Attestations remain verbatim-enforced;
blinding-leak scanning covers reconciliation output.

FR-6 **Enriched reporting.** The Diagnostic Report adds: judge provenance on
every dimension assessment; per-dimension and overall agreement statistics
replacing pass-variance; a **Dissent & Reconciliation annex** listing every
divergence, each judge's verdict + anchor, the ruling, and its evidence; lift
uncertainty derived from inter-judge spread (both per-judge lifts shown).
Mode B review report gains the same: consensus findings, dissent-flagged
recommendations.

FR-7 **Mode B dual-judge review.** Both judges execute each `review` packet;
findings/recommendations are merged by consensus with the same
reconcile-or-dissent discipline.

FR-8 **Checkpoint (D.5).** The blinded checkpoint panel is always built and
recorded (totals per lane, agreement rate, dissent count, mapping floor,
release summary). Default: auto-approved with `checkpoint_approved_by = "auto
(pre-authorized at intake)"`. If the pausing option was chosen at upload, the
run halts at `awaiting_checkpoint` for one approve/stop decision.

FR-9 **Deliverables.** Download keys (whitelisted; the escrow is never
served): report, score_sheet_a, score_sheet_b, content_mapping, release_a,
release_b, lift, run_record, diagnostic_bundle. Score sheets show Judge A /
Judge B / Consensus columns per sub-criterion.

FR-10 **Billing safety.** Unchanged and non-negotiable: the server contains no
model client; runner guards G1 (refuse `ANTHROPIC_API_KEY` /
`ANTHROPIC_AUTH_TOKEN`; scrub always), G2 (refuse `apiKeyHelper` / env
injection in Claude settings), G3 (key-free preflight), G4 (per-call
nonzero-cost tripwire), G5 (usage ledger); server rejects any packet result
reporting nonzero `total_cost_usd` with HTTP 402 and halts the run.
`CLAUDE_CODE_OAUTH_TOKEN` is sanctioned and never scrubbed. Gemini bills
Google only; `GEMINI_API_KEY` required for panel operation; free-tier keys are
refused unless `W2_ALLOW_GEMINI_FREE_TIER=1` (pilot only — Google may train on
free-tier data; commercial use excluded).

FR-12 **Self-service runner installation.** The server serves
`GET /install.sh` — a personalized installer (server URL + the member's token
baked in) that: installs Claude Code if missing; opens the member's browser
into Anthropic's own login for their Team seat (`claude setup-token`), so the
subscription credential is minted and stored on the member's laptop only;
installs the runner as a user-level background service (launchd / systemd
--user); writes `~/.w2/env`; runs the billing-guard and Gemini preflights;
and sends a first heartbeat. The console shows per-member runner status
("your runner: connected · last seen 12s ago") from heartbeats. In-app
subscription login is explicitly NOT built (policy: subscription OAuth is
scoped to Claude Code/claude.ai; credentials never live in shared cloud
infrastructure).

FR-13 **Owner-pays runner affinity.** `W2APP_TOKENS` maps member → token.
Runs are stamped with `owner` at upload (from the presenting token); packets
of a run are claimable only by a runner presenting that owner's token. Result:
the uploader's seat pays for their deal's evaluation — clean per-seat
attribution on the Team plan, no coordination rules between members. A run
whose owner's laptop is asleep waits in `awaiting_packets` and resumes on
reconnect (acceptable at weekly cadence; the console says so plainly).

FR-11 **Deployment.** One-command Cloud Run deploy (source build, GCS volume
at `/data`, `--max-instances 1`, shared-secret `W2APP_TOKEN` on all `/api`
routes). Runner ships with systemd unit and optional container; installed
once.

## 6. Success metrics

- SM-1: Operator actions per completed hands-free Mode A run = 1 (the upload).
- SM-2: Reported Anthropic API cost per run = $0.00 (usage ledger + tripwire
  never fired).
- SM-3: Subscription input tokens per Mode A run at 20k-word documents ≤ 500k
  (measured v1.1 baseline ~1.1M).
- SM-4: 100% of report scoring claims carry judge provenance; 100% of
  divergences appear in the annex (validated by R26/R27).
- SM-5: Mock-mode smoke (`scripts/smoke_e2e.sh`) green on both modes,
  including a seeded-divergence consensus path.

## 7. Locked decision log (binding on all documents)

| # | Decision | Value |
|---|---|---|
| D1 | Scoring protocol | One pass per judge per lane×dim-group (2 judges) |
| D2 | Judges | judge A `claude-code` (subscription), judge B `gemini` (API) |
| D3 | Reconciliation executor | Claude Code, blinded, evidence-ruled |
| D4 | Unresolved conflicts | Conservative default (weaker verdict / lower score) + recorded dissent; never operator-escalated |
| D5 | D.5 checkpoint default | Hands-free auto-approve (panel still recorded); pausing is opt-in |
| D6 | Five-pass protocol | Retired from UI; engine flag `EVAL_PROTOCOL` retains it for regression only |
| D7 | Gemini access | API key only (CLI consumer OAuth prohibited/deprecated June 2026); default model env `GEMINI_MODEL`, fallback `gemini-2.5-flash` |
| D8 | Gemini free tier | Refused by default (training/commercial terms); override env for pilots |
| D9 | Reliability statistic | Cross-judge agreement (verdict agreement rate + score concordance) replaces five-pass stddev/ICC |
| D10 | Lift uncertainty | Inter-judge spread: consensus lift headline, per-judge lifts as band |
| D11 | Engine version | v4.6 → v4.7; contracts remain the single source of truth |
| D12 | Operator involvement | Setup once; upload once per run; nothing else required |
| D13 | Cadence & topology | Per-deal (~weekly) runs; one personal runner per evaluating member on their own laptop; owner-pays affinity (FR-13) |
| D14 | In-app Team login | Prohibited/infeasible (credential policy); replaced by the personalized install-link flow (FR-12) with login occurring on the member's machine |

## 8. Constraints and compliance

- Anthropic credential policy (Feb 2026): consumer OAuth tokens are valid only
  inside Claude Code / claude.ai; plan credit is per-user, non-poolable, sized
  for individual automation. Therefore the runner executes on
  operator-controlled compute under the operator's login or
  `claude setup-token`; it is never containerized into the public Cloud Run
  service. `claude -p` under subscription draws plan limits, no API invoice.
- Google Gemini terms: individual-tier Gemini CLI serving ended 2026-06-18;
  API free tier is Flash-only, trains on prompts, excludes commercial use.
  Client material requires a paid-tier key (≈ $0.10/run at Flash pricing,
  ~212k in / ~10k out tokens).
- Frozen calibration: ZMS v4.x criteria (99 = 58 Zennify + 41 Well-Architected,
  22 sub-criterion mapping) are read-only inputs; v2.0 changes scoring
  protocol, not calibration content.
- Blinding: the `.lane-mapping` escrow is written at intake, never served by
  any route, never read by packet builders, and first read at reveal (batch 7).

## 9. Token budget (per run, 20k-word documents ≈ 28k tokens each)

Fixed scoring-packet overhead (measured): discipline 7.5k + dim reference
~2.5k + SA playbook 4.6k + calibration slice ~9.4k ≈ 25k; + SDD 28k ≈ **53k
input per scoring packet**.

| Mode A | Claude (subscription) | Gemini (Google) |
|---|---|---|
| components + features (2 lanes) | ~114k in | — |
| scoring (2 lanes × 2 groups × 1/judge) | ~212k in | ~212k in |
| reconciliation (≤4 packets, divergence-driven) | ≤ ~130k in | — |
| narratives + exec narrative | ~21k in | — |
| **totals** | **~350–480k in / ~40k out** | **~212k in / ~10k out** |

Mode B: ~190k Claude / ~96k Gemini. Prompt caching may reduce effective cost
(25k fixed overhead repeats across packets).

## 10. Release criteria

All FRs demonstrable; SM-1..SM-5 met; smoke green in mock mode including
seeded divergence + dissent rendering in both reports; deploy script verified
against a live GCP project; README and this document set shipped in-repo.
