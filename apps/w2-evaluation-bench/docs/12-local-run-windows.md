# Running the whole bench on one Windows machine

The application is self-contained: server + console + runner + the
pre-intelligence layer all run locally. The cloud deployment is optional —
this guide is the single-machine path. Requirements: Windows 10/11,
Python 3.11+, Node's npm (for Claude Code), a browser.

## 1. Start the server (terminal 1)

```powershell
git clone https://github.com/accelerate-ctrl/Accelerate.git
cd Accelerate\apps\w2-evaluation-bench
powershell -ExecutionPolicy Bypass -File scripts\serve.ps1
```

First run creates a virtualenv and installs FastAPI/uvicorn. The console is
at **http://localhost:8000/bench**, the landing at **http://localhost:8000/**.
Run data lives in `%USERPROFILE%\.w2\bench-data`.

What runs automatically inside the server, before any model sees a document
(pre-intelligence v1.2, measured 100% on the gold corpus — doc 11):

| Stage | What it does |
|---|---|
| Intake lint | prompt-injection + blinding-token scan on the BRD/SDD |
| Document model | section map, requirement registry, mechanism inventory |
| Evidence location | per-criterion candidate snippets (advisory hints in packets) |
| Traceability | BRD→SDD coverage pre-map |
| **Self-crawled release evidence** | when "live evidence" is on, the server searches the web itself, keeps only `*.salesforce.com` results, and feeds them to the crosswalk — no web-capable judge needed; a judge packet is the automatic fallback if the crawl finds nothing |
| Post-judgment verification | weak evidence anchors flagged into reconciliation |

Environment switches (set before `serve.ps1` if needed):

| Variable | Default | Meaning |
|---|---|---|
| `W2APP_TOKENS` | *(unset = open local dev)* | `name:token` pairs; turns on member auth |
| `W2_GOOGLE_CLIENT_ID` | *(unset = gate off)* | Google sign-in; register `http://localhost:8000` as an Authorized JavaScript origin on the OAuth client to use it locally |
| `W2_EVIDENCE_SOURCE` | `crawl` | `judge` pins release evidence back to a web-capable judge packet |
| `EVAL_PROTOCOL` | `dual-judge` | `five-pass` runs the frozen legacy engine |

## 2. Start the runner (terminal 2)

The runner executes the judge packets (Claude via your subscription, Gemini
via the org key) and posts results back to the local server.

```powershell
cd Accelerate\apps\w2-evaluation-bench
notepad $env:USERPROFILE\.w2\env     # create if missing, add:
#   W2_SERVER=http://localhost:8000
#   W2APP_TOKEN=<your token, only if W2APP_TOKENS is set on the server>
#   GEMINI_API_KEY=<org paid-tier key>
#   W2_GEMINI_TIER=paid
python runner\w2_runner.py --server http://localhost:8000
```

Claude side: `npm install -g @anthropic-ai/claude-code`, run `claude` once,
sign in with the Team seat. Never set `ANTHROPIC_API_KEY` — the billing
guard refuses to start with it present (zero-API-spend guarantee).

Smoke-test the full pipeline without any model (mock intelligence):

```powershell
python runner\w2_runner.py --server http://localhost:8000 --engine mock --once
```

## 3. Run an evaluation

Open http://localhost:8000/bench → upload BRD + SDD(s) → the pipeline runs
S0→S5 with a single touch. Toggle **live evidence** on the run form to have
the server self-crawl Salesforce release currency for every mechanism the
SDD names. Reports and artifacts (including `pre-analysis-*.json` and
`release-evidence-review-*.json`) download from the run detail page.

## Notes

- The self-crawl uses keyless HTML search with the enriched per-mechanism
  queries, filters to Salesforce-controlled domains at retrieval (the same
  R23 rule the validator enforces), dedupes and caps deterministically, and
  is bounded by a 75-second per-lane deadline. Status classification still
  happens only in the engine's resolve step — retrieval never judges.
- Windows Defender/firewall may prompt on first `uvicorn` listen — allow
  local access only.
- The cloud instance (docs 08/09) runs the identical code; anything verified
  locally behaves the same there.

## Single-AI mode (Gemini only — no Claude anywhere)

If Claude Code access is unavailable or unwanted, run the judging entirely
on Gemini: two model tiers fill the two judge slots (Judge A = Gemini Pro,
Judge B = Gemini Flash), so the dual-judge consensus, dissents and
validation all still operate — one provider, one API key.

```powershell
$env:GEMINI_API_KEY = "<key>"; $env:W2_GEMINI_TIER = "paid"
python runner\w2_runner.py --server <bench-url> --token <token> --engine gemini
```

Pick **"Single AI — Gemini Pro + Flash cross-check"** in the run form's
Judging dropdown. Override tiers with `W2_GEMINI_MODEL_A` / `W2_GEMINI_MODEL_B`.
The billing guard's Anthropic checks are moot in this mode (no Claude
component exists); the Gemini paid-tier check still applies to client docs.
