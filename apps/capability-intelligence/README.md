# Zennify Capability Intelligence Agent

Production-grade, GCP-native, multi-agent consulting AI for managing the Zennify
4-Pillar / ~836-subcap financial-services digital-maturity capability catalogue.
Target deploy: **Google Cloud Run**.

This is the canonical implementation of the spec — see `ARCHITECTURE.md` for
the system map, and the per-batch sections of this README for what's live now.

---

## Status — Batch 2 (Knowledge Graph + lenses)

Batches 0 + 1 + 2 are live. The knowledge graph and the multi-lens projections
of the catalogue are fully usable.

**Batch 2 adds:**

- VC mapping ingest from sheet `21_VC_Mapping_PerSubcap` — 1,990 subcap × subvertical
  rows for Pillar 1
- 14 of the 28 spec node types populated: Pillar, Category, L1_Capability,
  Subcap, UseCase, UC_Tag, L3_Platform, L4_Feature, Theme, MaturityDescriptor,
  Subvertical, Cluster, VC_Stage, Persona
- 13 edge types: BELONGS_TO, USES_PLATFORM, USES_FEATURE, DELIVERED_BY,
  SUPPORTS_UC, TAGGED_AS, REFERENCES_THEME, HAS_MATURITY, MAPS_TO_STAGE,
  IN_CLUSTER, IN_SUBVERTICAL, APPLIES_TO, CONSUMED_BY
- 8 universal MECE value-chain clusters (VCC-01..08) with a heuristic
  classifier mapping subvertical-specific stage names to the correct cluster
  (unmatched stages fall to VCC-00 for review)
- 22 UC archetype tags grouped into 5 families (Strategic / Workflow /
  Communication / Governance & Risk / Reporting & Validation)
- 10 financial-services subverticals (RB / CU / CL / CIB / FC / WM / AM /
  RIA / IC / IB) with code aliases for column-header matching
- KG service (NetworkX) with: lazy-build + LRU cache invalidated on each
  ingest; centrality (degree / pagerank / betweenness / eigenvector);
  Louvain communities; shortest-path (directed first, undirected fallback);
  impact-analysis (>=50% loss in either direction); k-hop neighborhood
- Real pages: Knowledge Graph (Cytoscape + cose-bilkent layout, node-kind
  filter, max-render slider, centrality panel with metric switch),
  Value Chain Atlas (8 clusters, subvertical filter), Subvertical Compare
  (subcap × 10 subverticals), Maturity Heatmap (199 × M1..M5), Use Case
  Explorer (827 UCs grouped by tag-family), Platform Catalog (45 platforms
  by vendor, with subcap-usage counts)
- Backend tests: 17 new (KG build, KG algorithms, lenses, end-to-end);
  Frontend tests: 2 new (heatmap + atlas)

## Status — Batch 1 (Catalogue spine)

Batches 0 + 1 are live. The catalogue spine is fully usable: ingest a Pillar
workbook from Drive (or a local folder), browse it with multi-lens drilldown,
save snapshots, diff versions, and triage change flags.

**Batch 1 adds:**

- Drive folder watcher with auto-discovery (recursive subfolder scan, picks
  highest `v<x>.<y>` per pillar, excludes any name containing `inactive`)
- Per-pillar `Refresh` button + `Refresh all`; ingest runs are tracked
- Workbook parser (openpyxl) for the Pillar 1 v14 schema: subcaps, categories,
  L1, use cases, L3 platforms, L4 features, maturity descriptors (M1..M5),
  theme mappings, stories
- Repository abstraction: in-memory (dev) ↔ pymongo against
  Firestore-MongoDB-compatibility (prod)
- Catalogue version snapshots + version listing + field-level diff between
  any two versions
- Change-flag inbox with severity, kind, target; resolve workflow
- Real pages: Mission Control, Capability Explorer (sunburst + tree + search),
  Subcap Deep Dive, Version Timeline, Diff Viewer, Change Flags Inbox,
  Settings
- `scripts/setup.sh` — one-shot GCP bootstrap (APIs, SA, IAM, Firestore in
  MongoDB-compat mode, GCS buckets, BigQuery datasets, Artifact Registry)
- Pillars 2-4 auto-detect: when you upload a workbook to the corresponding
  Drive subfolder with the same `2_Capability_Map` schema as Pillar 1, the
  agent ingests it on the next refresh; mis-aligned schemas are flagged but
  the pillar is still tracked

**Batch 0 (still in place):**
- FastAPI app + health/ready + dev auth bypass
- 29 router modules (Batch 1 has activated 6: catalogue / sheets / versions /
  diffs / flags / settings)
- React shell with all 28 pages, brand tokens, sidebar groups
- docker-compose with Firestore + Pub/Sub + GCS emulators

**What's deliberately NOT in Batch 1:** SOW / Jira ingest (Batch 3), Knowledge
Graph (Batch 2), LLM calls (Batch 4), benchmarks (Batch 5), digest (Batch 7).

## Roadmap

| Batch | Status | What it adds |
|---|---|---|
| 0 | **shipped** | Foundation — shell, brand, all 28 routes/pages, emulators, tests, docs |
| 1 | **shipped** | Catalogue spine: Drive → Sheets → Firestore (MongoDB-compat) → Capability Explorer + Subcap Deep Dive + Diff Viewer + Mission Control + Change Flags + Settings |
| 2 | **shipped** | KG v1 (14/28 node kinds, 13 edge kinds, NetworkX) + Knowledge Graph page (Cytoscape) + Value Chain Atlas + Subvertical Compare + Maturity Heatmap + Use Case Explorer + Platform Catalog |
| 2 | planned | KG v1 + 9 lenses + Knowledge Graph page + Value Chain Atlas + Subvertical Compare + Maturity Heatmap + Use Case Explorer + Platform Catalog |
| 3 | planned | Internal evidence: SOWs (DLP redacted) + Jira + gen-stories; Story / SOW / Project–Subcap pages |
| 4 | planned | LLM router (Vertex Gemini + Anthropic Claude), 7-step consultant loop, 8 validation gates, adversarial agent, Reasoning Chain Viewer, AI Suggestions, Trends, News, hallucination detector |
| 5 | planned | Public filings + analyst + technographic ingest, AI extrapolation benchmarks, Benchmarks Studio |
| 6 | planned | Lifecycle engine + Manager, Vendor Intelligence, Client Journey + DMA handoff |
| 7 | planned | Quarterly Strategic Digest (Claude Opus), Deep Audit weekly, PPTX export |
| 8 | planned | RAG Chat, What-If Simulator, Persona views, Notifications, Exports, QA & Audit Dashboard, eval harness |
| 9 | planned | All 14 Cloud Run Jobs + Scheduler, Pub/Sub bus, Cloud Tasks DLQ, Cloud Build CI/CD, OpenTelemetry, IaC, finalized 6 docs |

---

## Quickstart (local — no GCP needed)

Prerequisites: Docker, Python 3.12, Node 20.

```bash
# from repo root
cd apps/capability-intelligence

# Backend tests (uses the attached Pillar 1 file in test-data/)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q

# Frontend tests
cd ../frontend
npm install
npm test -- --run

# Run end-to-end locally — points at test-data/ for catalogue ingest
cd ../backend
LOCAL_CATALOGUE_DIR=$(realpath ../test-data) \
LOCAL_REPOSITORY_PATH=$(realpath ../.local-repo.json) \
uvicorn app.main:app --reload --port 8080

# In another shell, refresh and browse
curl -X POST -H 'Authorization: Bearer dev-test@zennify.com' \
     localhost:8080/api/sheets/refresh
curl -H 'Authorization: Bearer dev-test@zennify.com' \
     localhost:8080/api/catalogue/overview | jq
```

## Cloud setup (run once)

```bash
# Optional: override the defaults
GCP_PROJECT_ID=digital-maturity-assessor REGION=us-central1 \
DRIVE_FOLDER_ID=1rF9zdx1qF7BJ9t21eFdvZQW11Y5dUjy3 \
  bash apps/capability-intelligence/scripts/setup.sh
```

The script enables APIs, creates a service account, grants IAM, creates the
Firestore database in MongoDB-compatibility mode (`dma-assessor` by default),
provisions GCS buckets and BigQuery datasets, sets up Artifact Registry,
generates a SA key file, and prints the env block to copy into `.env`.

After running, **share the Drive folder with the printed service-account
email** (Viewer permission). Then:

```bash
docker compose up --build -d
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
