# W2 Evaluation Bench v2.0 — dual-judge consensus

Zennify's Solutioning Evaluation Framework (Workflow 2, engine **v4.7**) as a
self-hosted web application. Upload a BRD plus two SDDs for a blinded
comparative evaluation (Mode A, methodology lift), or a BRD plus one SDD for a
qualitative review (Mode B). The application evaluates and reviews the
solution designs and produces the branded Diagnostic Report / SDD Review
Report — comprehensive, traceable, refinement-first — plus the full artifact
trail.

**v2.0 protocol: every scoring unit is judged once by each of two independent
model families** — Claude (via Claude Code, on the member's Team-plan seat)
and Gemini (via the Gemini API) — from byte-identical blinded packets. The
server deterministically diffs the two scorecards; divergences are reconciled
by a blinded, evidence-ruled Claude packet that must cite the SDD verbatim;
irreconcilable items are preserved as **dissents** and resolved conservatively
(weaker verdict / lower score) — nothing is ever silently averaged. Reports
carry judge provenance on every claim, per-dimension agreement statistics, a
Dissent & Reconciliation annex, and per-lane refinement areas. The v1.1
five-pass protocol is retired from the product and retained ONLY behind
`EVAL_PROTOCOL=five-pass` for regression comparison (PRD D6).

**Billing model: subscription tokens only.** Claude judgment runs through the
member's runner under their Claude Team seat (`claude -p` / Agent SDK plan
credit). There is no Anthropic client anywhere in the server — grep `server/`
for `anthropic` (smoke test T-9 does) — and the runner enforces five guards
(below) so a metered API call cannot happen silently. Gemini bills Google
only, on the org's **paid-tier** key (free tier is refused: Google may train
on free-tier prompts and excludes commercial use; override for non-client
pilots only with `W2_ALLOW_GEMINI_FREE_TIER=1`).

## Architecture

```
Browser ── landing (/) + operator console (/bench)
   │
FastAPI server (server/) ──────────── the deterministic brain, ZERO model calls
   ├─ orchestrator.py   state machine over the Mode A/B pipeline
   ├─ consensus.py      dual-judge diff / evidence-ruled merge / §6.5 stats
   ├─ engine/           vendored evaluate-sdd + zms v4.7 (contracts, R1-R28,
   │                    blinding escrow, crosswalk, lift, report builders)
   ├─ packets.py        work-packet store (claim/complete, per-judge ledger)
   └─ prompts.py        each act of model judgment as a self-contained packet
   │
   ▼ HTTP (poll; owner-pays affinity per member token)
w2_runner (runner/) ── each member's laptop, under THEIR Team seat
   ├─ billing_guard.py  G1-G5 subscription-only enforcement
   ├─ Judge A: `claude -p --output-format json` (subscription)
   ├─ Judge B: gemini_judge.py → Gemini API (Google-side billing, paid tier)
   └─ mock engine:      deterministic, judge-aware, seeded divergence (CI)
```

What runs where:

| Deterministic (server, no tokens) | Model judgment (runner) |
|---|---|
| intake, hashing, lane escrow | component discovery (per lane, Judge A) |
| ZMS load + engagement filter | feature extraction (per lane, Judge A) |
| content-mapping classify + Dim-4 floor | scoring: 1 packet per judge per lane×dim-group (8 total) |
| release crosswalk extract/resolve | reconciliation of divergences (Judge A, blinded, ≤4 packets) |
| scorecard diff, consensus merge, §6.5 agreement stats | per-lane narrative + citations (Judge A) |
| R1–R28 validation, sheets, consensus lift + judge lifts | executive narrative (pre-reveal, blinded) |
| reveal, .docx report builders | live release evidence (optional, web) · Mode B review ×2 judges |

Blinding is preserved end-to-end: the ZenAgent↔lane mapping lives only in the
run directory's `.lane-mapping` escrow, which is never served by any API route
and never read by the packet builder; judges see only "Output A/B"; R14 scans
every reasoning field AND all reconciliation output; `lane_reveal_apply.py` is
the escrow's first and only reader, at the reveal. Judge independence is
structural: the two scoring packets of a (lane, dim-group) are byte-identical
— the judge exists only in packet metadata — and neither judge ever sees the
other's output before reconciliation (attested verbatim in every bundle, R28).

## The five billing guards (runner) + server tripwire

- **G1** refuse to start if `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` is set;
  scrub both from every subprocess environment regardless.
- **G2** refuse if any Claude Code settings file defines `apiKeyHelper` or
  injects those variables.
- **G3** preflight probe: `claude -p` must succeed under the scrubbed (key-free)
  environment — proving the subscription login carries the call.
- **G4** per-call tripwire: any nonzero `total_cost_usd` in a Claude Code result
  aborts the runner (subscription-covered calls report no billable dollar cost).
- **G5** usage ledger: per-packet, per-judge token usage is posted to the server
  and shown in the console (`reported API cost $0.00 (must stay 0.00)`).
- **Server tripwire**: independently rejects any packet result reporting a
  nonzero cost (HTTP 402) and halts the run loudly. Malformed results are
  rejected with HTTP 400 and never stored (the packet stays open); results are
  write-once; a result reporting execution by the wrong judge is refused
  (provenance integrity, TR-8).

Per Anthropic's guidance for subscription-only execution: `claude logout &&
claude login` with your plan credentials only, and keep Console/API credits
detached from that login. `CLAUDE_CODE_OAUTH_TOKEN` (from `claude
setup-token`) is the sanctioned headless credential and is never scrubbed.

## Cloud Run deployment (hands-free system)

```bash
PROJECT=my-gcp-project \
W2APP_TOKENS="alice:$(openssl rand -hex 16),bob:$(openssl rand -hex 16)" \
  bash scripts/deploy_cloudrun.sh
```

Builds from source, mounts a GCS bucket at `/data`, pins `--max-instances=1`
(single-writer file store), protects every `/api` route with per-member
tokens, and finishes by running `scripts/remote_smoke.sh` against the live
URL (health, auth walls, traversal block, runner payload — the deploy fails
loudly if the service isn't the one the release gate certified). Full
component-by-component plan: `docs/08-cloud-run-deployment-guide.md`;
deploying straight from GitHub (Cloud Shell first deploy + push-to-deploy
Cloud Build trigger): `docs/09-github-deploy-user-guide.md`; QA & security
audit: `docs/qa-report.md`. The bench protects itself with per-member
tokens (`W2APP_TOKENS="member:token,..."`; the single `W2APP_TOKEN` is still
honoured as member "operator"). **Owner-pays affinity (FR-13):** each run is
stamped with the uploading member's id, and only that member's runner is
offered its packets — every member's seat pays for their own deals, no
coordination needed. A run whose owner's laptop is asleep waits in
`awaiting_packets` and resumes on wake ("waiting for your runner" in the
console — acceptable at weekly cadence).

Each evaluating member installs their personal runner ONCE (full guide:
`docs/07-installation-guide.md`):

```bash
curl -fsSL https://<bench-url>/install.sh | bash -s -- --token <their-token>
```

The installer adds Claude Code if missing, opens Anthropic's own login for
their Team seat (`claude setup-token` — the credential never leaves their
machine; in-app login is deliberately NOT built, PRD D14), installs the runner
as a user-level service (launchd / `systemd --user`), writes `~/.w2/env`
(0600), and runs `w2_runner.py --selfcheck` (billing guard + Gemini tier +
bench reachability). The console header then shows "your runner: connected".

Why the runner does not live inside Cloud Run: Anthropic's credential policy
scopes consumer OAuth (subscription) tokens to Claude Code and claude.ai;
plan credit is per-seat and non-poolable. Running Claude Code under each
member's own login on compute they control is exactly that use; baking a
token into a multi-tenant web service is not. The packet protocol exists
precisely so the app can live in the cloud while the subscription-billed
judgment stays on the member's side of the line.

## Quickstart (local)

```bash
pip install -r requirements.txt
bash scripts/serve.sh 8787
# open http://localhost:8787 (landing) → /bench (console), upload BRD + SDD(s)

# the dual-judge runner (panel is the default engine):
GEMINI_API_KEY=... W2_GEMINI_TIER=paid \
  python3 runner/w2_runner.py --server http://localhost:8787
# demo / CI without any model:
python3 runner/w2_runner.py --server http://localhost:8787 --engine mock --once
```

Mode A is **one-touch**: upload, then nothing — the D.5 checkpoint is
auto-approved by default (the blinded panel is still built and recorded for
audit). Opt into a pausing checkpoint per run in the console. Everything else
is automatic; deliverables appear as download links.

`scripts/smoke_e2e.sh` is the release gate: both modes hands-free + paused,
seeded dissents asserted end-to-end, billing tripwire, write-once, shape
rejection, auth/affinity matrix, escrow reachability, SDK greps, and the
frozen five-pass legacy leg. It must print `SMOKE PASS`.

## Options

- **Live release evidence**: "Release evidence: Live via runner" at upload;
  only `*.salesforce.com` URLs can assert a status (R23).
- **`W2APP_DATA`** relocates the data directory.
- **`GEMINI_MODEL`** overrides the Gemini model (default `gemini-2.5-flash`).
- **`EVAL_PROTOCOL=five-pass`** boots the frozen v1.1 protocol (regression
  only; not exposed in the UI).
- Multi-runner: several runners per member are fine; stale claims (>90s) are
  taken over by the same owner's runners only.

## What the mock engine is (and is not)

`--engine mock` produces schema-correct, R1–R28-valid results with zero model
calls — now judge-aware: the Gemini side deterministically diverges on ~15% of
criteria (the first criterion of every slice guaranteed), the reconcile
handler rules with verbatim SDD citations and returns ≥1 forced dissent per
run, so consensus, reconciliation, conservative resolution, and the report
annex are exercised end-to-end in CI. Its judgments are placeholders — real
evaluations require the panel.
