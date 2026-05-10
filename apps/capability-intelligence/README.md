# Zennify Capability Intelligence Agent

Production-grade, GCP-native, multi-agent consulting AI for managing the Zennify
4-Pillar / ~836-subcap financial-services digital-maturity capability catalogue.
Target deploy: **Google Cloud Run**.

This is the canonical implementation of the spec — see `ARCHITECTURE.md` for
the system map, and the per-batch sections of this README for what's live now.

---

## Status — Batch 0 (Foundation)

Batch 0 ships the **shell and contract**, not the intelligence. Everything that
later batches add hangs off of structures defined here.

**What's working in Batch 0:**

- FastAPI app with health + readiness endpoints (real)
- 29 router modules registered, each exposing a `GET /_stub` (auth-required)
  that reports its activating batch
- Firebase ID token verifier with a dev-mode bypass (`Bearer dev-<email>`,
  domain-restricted to `zennify.com`)
- React 18 + Vite + TypeScript SPA shell
- Tailwind theme with the 8 Zennify brand tokens, source-tier chip palette,
  claim-label badge palette, cluster colors
- Sidebar with **all 28 pages** grouped per spec §13 (most are
  `<PageStub batch={n} />` placeholders)
- Local stack via `docker-compose` (Firestore + Pub/Sub + GCS emulators)
- Pytest suite (`tests/unit`, `tests/integration`); Vitest suite; Playwright
  smoke
- Canonical source registry (50+ sources tier-stratified) in
  `config/canonical_sources.yml`
- 9 personas, 9 lenses defined as YAML
- 14 Cloud Run Job placeholders in `backend/jobs/`
- `.env.example` documenting every environment variable across all batches

**What's deliberately NOT in Batch 0:** any real ingestion (Sheets, Drive, SOW,
Jira, news), any LLM calls, any Firestore writes, any KG, any benchmarks,
any digest. See `INPUT_CHECKLIST.md` for what each later batch requires.

## Roadmap

| Batch | Status | What it adds |
|---|---|---|
| 0 | **shipping** | Foundation — shell, brand, all 28 routes/pages, emulators, tests, docs |
| 1 | next | Catalogue spine: Drive → Sheets → Firestore + BQ → Capability Explorer + Subcap Deep Dive + Diff Viewer + Mission Control + Settings |
| 2 | planned | KG v1 + 9 lenses + Knowledge Graph page + Value Chain Atlas + Subvertical Compare + Maturity Heatmap + Use Case Explorer + Platform Catalog |
| 3 | planned | Internal evidence: SOWs (DLP redacted) + Jira + gen-stories; Story / SOW / Project–Subcap pages |
| 4 | planned | LLM router (Vertex Gemini + Anthropic Claude), 7-step consultant loop, 8 validation gates, adversarial agent, Reasoning Chain Viewer, AI Suggestions, Trends, News, hallucination detector |
| 5 | planned | Public filings + analyst + technographic ingest, AI extrapolation benchmarks, Benchmarks Studio |
| 6 | planned | Lifecycle engine + Manager, Vendor Intelligence, Client Journey + DMA handoff |
| 7 | planned | Quarterly Strategic Digest (Claude Opus), Deep Audit weekly, PPTX export |
| 8 | planned | RAG Chat, What-If Simulator, Persona views, Notifications, Exports, QA & Audit Dashboard, eval harness |
| 9 | planned | All 14 Cloud Run Jobs + Scheduler, Pub/Sub bus, Cloud Tasks DLQ, Cloud Build CI/CD, OpenTelemetry, IaC, finalized 6 docs |

---

## Quickstart (local)

Prerequisites: Docker, Python 3.12, Node 20.

```bash
# from repo root
cd apps/capability-intelligence

# Backend tests (no docker needed)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q

# Frontend tests
cd ../frontend
npm install
npm test -- --run

# Full local stack (API + emulators)
cd ..
docker compose up --build -d
curl -fsS localhost:8080/api/health
docker compose down
```

### API quick check

```bash
# Health (no auth)
curl localhost:8080/api/health

# Stub of any router (auth required)
curl -H 'Authorization: Bearer dev-test@zennify.com' \
     localhost:8080/api/catalogue/_stub
```

---

## Repository layout (Batch 0)

```
apps/capability-intelligence/
├── backend/           FastAPI app, routers (29), models, tests, 14 job placeholders
├── frontend/          Vite + React + TS shell, 28 pages, Tailwind, vitest, Playwright
├── config/            canonical_sources, personas, lenses, peer_cohorts, …
├── infra/             Cloud Run / Cloud Build / BQ / DLP placeholders (Batch 9)
├── Dockerfile         Multi-stage: Node build → Python runtime
├── docker-compose.yml api + Firestore + Pub/Sub + GCS emulators
├── .env.example       Env vars across all batches
├── ARCHITECTURE.md    System architecture (placeholder TOC; built batch-by-batch)
├── OPERATOR_GUIDE.md  How to operate the live system
├── RUNBOOK.md         Incident response
├── COST_GUIDE.md      Per-feature cost estimates and routing
├── DATA_DICTIONARY.md Every collection / table / node / edge / metric
└── INPUT_CHECKLIST.md What inputs each batch needs
```

## Architecture (one-paragraph summary)

Single Cloud Run service hosts both the React SPA (mounted as static files) and
the FastAPI `/api`. Long-running ingestion and AI work goes to **Cloud Run
Jobs** triggered by Cloud Scheduler. **Vertex Gemini 2.5 Flash/Pro is the LLM
workhorse**; **Anthropic Claude Sonnet 4.6 / Opus 4.7 is reserved for
high-leverage reasoning** (adversarial review, contradiction resolution,
quarterly digest, deep audit). Operational state in Firestore; analytical
state in BigQuery; vector search in Vertex AI; PII redaction via Cloud DLP.
Auth is Firebase with a `@zennify.com` domain restriction. Every AI output
carries claim labels, source-tier chips, ERS scores, and a reasoning-chain
link — no black-box outputs. See `ARCHITECTURE.md`.

## Cost discipline

Per spec §3, model routing is locked. Daily spend ceiling and weekly
Anthropic budget are configurable; auto-throttle at 90% of ceiling. See
`COST_GUIDE.md` (filled in Batch 4 onwards).

## Security & compliance

Firebase Auth + Google + `@zennify.com` domain restriction. SOWs pass through
Cloud DLP before any LLM call. All audit events stream to BigQuery
`audit_events` with 7-year retention. Every AI output is accompanied by its
reasoning chain. Citations are URL-verified daily. See `RUNBOOK.md`.

## License

Internal — Zennify confidential.
