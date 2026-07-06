# W2 Evaluation Bench

Zennify's Solutioning Evaluation Framework (Workflow 2, engine v4.6) as a
self-hosted web application. Upload a BRD plus two SDDs for a blinded
comparative evaluation (Mode A, methodology lift), or a BRD plus one SDD for a
qualitative review (Mode B). The application runs the pipeline and produces the
branded Diagnostic Report / SDD Review Report plus the full artifact trail.

**Billing model: subscription tokens only.** Every act of model judgment runs
through the operator-side runner under YOUR Claude subscription (the monthly
Agent SDK / `claude -p` credit on Pro, Max, Team and Enterprise plans). There
is no Anthropic API client anywhere in the server — grep `server/` for
`anthropic` — and the runner enforces five guards (below) so a metered API
call cannot happen silently.

## Architecture

```
Browser ── operator console (server/static)
   │
FastAPI server (server/) ──────────── the deterministic brain, ZERO model calls
   ├─ orchestrator.py   state machine over the 15-batch Mode A pipeline
   ├─ engine/           vendored evaluate-sdd + zms v4.6 (contracts, R1-R25,
   │                    blinding escrow, crosswalk, lift stats, report builders)
   ├─ packets.py        work-packet store (claim/complete, usage ledger)
   └─ prompts.py        each act of model judgment as a self-contained packet
   │
   ▼ HTTP (poll)
w2_runner (runner/) ── on the operator's machine, under their subscription
   ├─ billing_guard.py  G1-G5 subscription-only enforcement
   ├─ claude-code engine: `claude -p --output-format json` per packet
   └─ mock engine:       deterministic model-free intelligence (demo/CI)
```

What runs where:

| Deterministic (server, no tokens) | Model judgment (runner, subscription) |
|---|---|
| intake, hashing, lane escrow | component discovery (per lane) |
| ZMS load + engagement filter | feature extraction (per lane) |
| content-mapping classify + Dim-4 floor | 20 scoring passes (2 lanes x 2 dim-groups x 5) |
| release crosswalk extract/resolve | per-lane narrative + citations |
| pass record/aggregate, ICC stats | executive narrative (pre-reveal, blinded) |
| R1-R25 validation, sheets, lift | live release evidence (optional, web) |
| reveal, .docx report builders | Mode B qualitative review (2 packets) |

Blinding is preserved end-to-end: the ZenAgent↔lane mapping lives only in the
run directory's `.lane-mapping` escrow, which is never served by any API route
and never read by the packet builder; the runner sees only "Output A/B"; R14
scans every reasoning field; `lane_reveal_apply.py` is the escrow's first and
only reader, at batch 7.

## The five billing guards (runner) + server tripwire

- **G1** refuse to start if `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` is set;
  scrub both from every subprocess environment regardless.
- **G2** refuse if any Claude Code settings file defines `apiKeyHelper` or
  injects those variables.
- **G3** preflight probe: `claude -p` must succeed under the scrubbed (key-free)
  environment — proving the subscription login carries the call.
- **G4** per-call tripwire: any nonzero `total_cost_usd` in a Claude Code result
  aborts the runner (subscription-covered calls report no billable dollar cost).
- **G5** usage ledger: per-packet token usage is posted to the server and shown
  in the console so plan-credit consumption is visible per run.
- **Server tripwire**: independently rejects any packet result reporting a
  nonzero cost (HTTP 402) and halts the run loudly.

Per Anthropic's guidance for subscription-only execution: `claude logout &&
claude login` with your plan credentials only, and keep Console/API credits
detached from that login.

## Cloud Run deployment (hands-free system)

The intended production shape: **Cloud Run hosts the application; Claude Code
runs in the background on your own machine or VM as the intelligence layer.**
The runner polls outbound over HTTPS, so it needs no inbound ports, no static
IP, and no credentials on Google's side.

```bash
PROJECT=my-gcp-project W2APP_TOKEN=$(openssl rand -hex 24) \
  bash scripts/deploy_cloudrun.sh
```

This builds from source, mounts a GCS bucket at `/data` (run state, escrow,
deliverables survive restarts), pins `--max-instances=1` (the file-based
orchestrator assumes a single writer), and protects every `/api` route with
the `X-W2-Token` shared secret. The console prompts for the token on first use.

On the operator side, install the runner once as a daemon and forget it:

```bash
# headless credential (one-time, on any browser machine):
claude setup-token          # prints sk-ant-oat01-... (1 year, subscription-billed)
# on the runner box:
export CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...
python3 runner/w2_runner.py --server https://<cloud-run-url> --token <W2APP_TOKEN>
# or: examples/w2-runner.service (systemd) / Dockerfile.runner (container)
```

Why the runner does not live inside Cloud Run: Anthropic's credential policy
scopes consumer OAuth (subscription) tokens to Claude Code and claude.ai, sized
for individual automation; plan credit is per-user and non-poolable. Running
Claude Code under your own login on compute you control is exactly that use;
baking your token into a multi-tenant web service is not. The packet protocol
exists precisely so the app can live in the cloud while the subscription-billed
judgment stays on your side of the line. For hands-free Mode A runs, tick
"Hands-free (pre-approve D.5)" at upload — the checkpoint panel is still built
and recorded for audit, the run just doesn't pause on it.

## Multi-LLM judge (panel mode)

`--engine panel` turns the five-pass scoring discipline into a cross-model
panel: Claude Code executes everything except the scoring passes listed in
`--gemini-passes` (default `4,5`), which are judged by Gemini via the Gemini
API (`GEMINI_API_KEY`). Because each pass is already an independent cold read,
a Gemini-judged pass slots into the aggregate exactly like any other — so
cross-MODEL disagreement shows up honestly in the per-dimension stddev, the
variance flags, and the ICC-widened lift uncertainty band, instead of being
silently averaged. Judge provenance is recorded per packet in the usage ledger,
and the run's evaluator is labelled `panel:claude-code+gemini` at upload.

Billing: Gemini calls bill Google, never the Anthropic API — the zero-Claude-
API-spend guarantee is unchanged. Mind Google's terms: the AI Studio free tier
(Flash models only since April 2026) may use prompts for training and excludes
commercial use, so client SDDs need a paid-tier key (typically cents per run;
~8 Gemini pass-turns x ~26k tokens in a Mode A run). Gemini CLI's consumer
OAuth route is deliberately NOT used: Google ended individual-tier CLI serving
in June 2026 and treats third-party OAuth use as abuse; the API key is the
supported programmatic surface.

## Quickstart

```bash
pip install -r requirements.txt
bash scripts/serve.sh 8787          # local; see Cloud Run section for production
# open http://localhost:8787, upload BRD + SDD(s)

# on the operator machine (same or different host):
python3 runner/w2_runner.py --server http://localhost:8787 --engine claude-code
# demo / CI without a model:
python3 runner/w2_runner.py --server http://localhost:8787 --engine mock --once
```

Mode A pauses once, at the mandatory blinded D.5 checkpoint — approve in the
console (or `POST /api/runs/{id}/approve {"approve": true}`) and, if the
executive-narrative packet is created after approval, let the runner drain it.
Everything else is automatic. Deliverables appear as download links.

`scripts/smoke_e2e.sh` runs both modes end-to-end in mock mode against the
bundled fixtures and asserts the reports render.

## Options

- **Live release evidence**: set "Release evidence: Live via runner" at upload.
  The crosswalk's per-mechanism queries become a web-enabled packet the runner
  executes with Claude Code's web tools; only `*.salesforce.com` URLs can
  assert a status (R23). Default is the dated register (offline, never
  penalises unverified mechanisms).
- **`W2APP_DATA`** env var relocates the data directory.
- Multi-runner: several runners can poll the same server; claims stale after
  90s are taken over.

## What the mock engine is (and is not)

`--engine mock` produces schema-correct, R1-R25-valid results with zero model
calls: verdicts from keyword coverage, anchors as verbatim SDD slices. It
exists so the pipeline, validators, blinding round-trip, and report builders
can be exercised in CI and demos. Its judgments are placeholders — real
evaluations require the claude-code engine.
