# Inputs required by batch

Batch 0 needs nothing. Each later batch is gated on the inputs below. Provide
them at the start of the batch (or earlier so I can wire them in parallel).

## Batch 1 — Catalogue spine — ✅ supplied

- [x] Drive folder: `1rF9zdx1qF7BJ9t21eFdvZQW11Y5dUjy3` (each pillar in a
      subfolder; agent picks the highest-version, non-`inactive` file per pillar)
- [x] GCP project: `digital-maturity-assessor`
- [x] Region: `us-central1`
- [x] Firestore database: `dma-assessor` (MongoDB-compatibility mode)
- [x] Setup approach: `scripts/setup.sh` (run once with your gcloud auth)
- [ ] **Manual step after setup.sh runs**: share the Drive folder with the
      service-account email printed by the script (Viewer permission)
- [ ] **Manual step after Firestore DB creation**: copy the MongoDB endpoint
      host from Cloud Console into `FIRESTORE_MONGO_URI` in `.env`
- [ ] Firebase project ID for production auth (current: dev-mode bypass works)
- [ ] Allowed Firebase Auth domain (default `zennify.com`)

## Batch 3 — Internal evidence — partially supplied

- [x] gen_stories_export.xlsx (already attached + ingested in dev)
- [ ] Drive shared-drive ID for SOWs, with `active|prospect|inactive|archived`
      subfolders. Without this, the system runs on `test-data/SOWs/`.
      Set `DRIVE_SOWS_FOLDER_ID` in `.env` and share the folder with the
      service-account email.
- [ ] Atlassian Cloud URL (e.g., `zennify.atlassian.net`) — set
      `JIRA_BASE_URL`
- [ ] Jira service-account email + API token — set `JIRA_EMAIL` +
      `JIRA_API_TOKEN`
- [ ] List of Jira project keys to ingest — set `JIRA_PROJECT_KEYS=["KEY1","KEY2"]`

## Batch 4 — LLM core — partially supplied

- [x] Architecture in place; runs end-to-end in deterministic dev mode
      (`LLM_LIVE_MODE=false`) with no external creds.
- [ ] Anthropic API key (`ANTHROPIC_API_KEY`, stored in Secret Manager)
- [ ] Vertex AI region (`VERTEX_REGION`, default `us-central1`)
- [ ] GCP project ID (`GCP_PROJECT_ID`) for Vertex Gemini + embeddings
- [ ] Anthropic weekly $ budget cap (`ANTHROPIC_WEEKLY_BUDGET_USD`,
      auto-degrades to Gemini at `COST_THROTTLE_PCT` × budget)
- [ ] Daily total $ spend ceiling (`DAILY_SPEND_CEILING_USD`,
      Cloud Monitoring alert at 80%, hard throttle at 90%)
- [ ] Optional: `NEWS_FEEDS` array of RSS URLs for live news ingest
- [ ] Confirm pinned model IDs (defaults already set):
      - Sonnet → `claude-sonnet-4-6`
      - Opus → `claude-opus-4-7`
      - Embeddings → `text-embedding-005`
      - Gemini Flash → `gemini-2.5-flash`
      - Gemini Pro → `gemini-2.5-pro`
- [ ] Flip `LLM_LIVE_MODE=true` once keys are loaded — no other code change.

## Batch 6 — Lifecycle + Vendor Intelligence + Client Journey — fully supplied

- [x] No new external creds required — Batch 6 reads what's already in
      the catalogue + benchmarks + news + SOWs + stories.
- [x] DMA App handoff schema defined as `dma-handoff-v1`. If the DMA
      App expects a different field shape, adjust
      `client_journey_service.dma_packet()`.

## Batch 5 — Benchmarks — partially supplied

- [x] Architecture in place; runs end-to-end in dev mode against
      synthetic seed filings + analyst extracts + technographics in
      `test-data/`.
- [x] FDIC asset-size-bucket bootstrap cohorts pre-seeded in
      `config/peer_cohorts.yml` (5 cohorts).
- [ ] **Legal sign-off note** for Gartner / Forrester / Celent / IDC
      ingestion and LinkedIn / Indeed / BuiltWith / Wappalyzer
      technographic ingest.  Flagged here so it's on record.
- [ ] BuiltWith / Wappalyzer API keys (`BUILTWITH_API_KEY`,
      `WAPPALYZER_API_KEY`); without them the engine reads seed JSONs.
- [ ] LinkedIn approach: official People/Jobs API, third-party
      (Bright Data / Phantombuster), or accept ToS risk.
- [ ] SEC EDGAR User-Agent email (`SEC_EDGAR_EMAIL`) for live filings.
- [ ] Optional cohort overrides in `config/peer_cohorts.yml` if the
      FDIC bucket bootstrap doesn't fit a target sub-vertical.

## Batch 7 — Strategic digest

- [ ] Zennify logo (PNG + SVG)
- [ ] Confirm 8-token brand palette (already locked from spec §14)
- [ ] Optional `.pptx` template if one exists; else the digest export ships in
      a clean Zennify-branded layout
- [ ] Confirm "5 historical quarters of curated priorities" do not exist; if so
      I'll bootstrap synthetic golden labels for the digest eval

## Batch 9 — Production hardening

- [ ] Slack webhook URL for alerts (optional)
- [ ] Approver UIDs / emails for the breaking-change gate
- [ ] DMA App handoff schema if it exists; else I publish v1 and you integrate

---

## Outstanding clarifications (any time)

- Daily spend ceiling `$X` value
- Anthropic weekly cap `$X/week` value
- DMA App existing handoff schema (v0 if any)
- Whether ARM / x86 deploy target matters (default x86 amd64)
