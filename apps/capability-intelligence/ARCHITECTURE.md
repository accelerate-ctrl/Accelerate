# Architecture

> Filled in batch-by-batch. Each batch appends or revises the relevant section
> rather than rewriting the whole doc.

## TOC

1. System diagram (ASCII) — Batch 9
2. Data flow per major operation — Batch 9
3. Multi-agent topology — Batch 4
4. Validation gate flow — Batch 4
5. Knowledge graph schema — Batch 2
6. Lens model — Batch 2
7. Benchmark extrapolation pipeline — Batch 5
8. Quarterly digest synthesis — Batch 7
9. Cost & routing — Batch 4
10. Security & compliance — Batch 9
11. ADRs — appended as decisions are made

## Batch 9 — Production hardening

```
                              ┌─────────────────────────────┐
                              │      Cloud Scheduler        │
                              │   (14 cron entries, UTC)    │
                              └─────────────┬───────────────┘
                                            │ HTTP OAuth
                                            ▼
              ┌──────────────────────────────────────────────────┐
              │            Cloud Run Jobs (14 total)             │
              │  one container image, JOB_NAME-dispatched         │
              │     python -m app.jobs.runner <job_name>         │
              └──────────────────────────────────────────────────┘
                          │
                          │ structured logs + spans  ──▶  Cloud Trace + Cloud Logging
                          │ events                   ──▶  Pub/Sub (5 topics)
                          │                                   │
                          │                                   ▼
                          │                       ┌────────────────────────┐
                          │                       │ Cloud Tasks DLQ        │
                          │                       │ (3 retries / 64s back) │
                          │                       └────────────────────────┘
                          ▼
              ┌──────────────────────────────────────────────────┐
              │       Repository (Firestore-Mongo / Mongo)       │
              └──────────────────────────────────────────────────┘
                          ▲
                          │
              ┌──────────────────────────────────────────────────┐
              │            Cloud Run service (api)               │
              │    same image; install_telemetry() on boot;      │
              │    serves /api/* + the SPA from /app/static      │
              └──────────────────────────────────────────────────┘
                          ▲
                          │   HTTPS  + OAuth (Firebase auth)
                          │
                       Browser
```

The 14 jobs (with cron + service hookup):

| Job                            | Cron               | Service called |
|--------------------------------|--------------------|----------------|
| news_poll                      | hourly             | `news_service.refresh()` |
| jira_incremental               | every 15 min       | `stories_service.ingest_jira()` |
| sow_incremental                | hourly             | `sow_service.ingest_all()` |
| public_filings_poll            | daily 04:30 UTC    | `benchmarks_service.refresh(extrapolate=False)` |
| lifecycle_scoring_daily        | daily 06:30 UTC    | `lifecycle_service.recompute_all()` |
| citation_verify_daily          | daily 03:00 UTC    | `citation_verifier.verify_citation` over `citation_probes` |
| drift_check_daily              | daily 07:30 UTC    | adjacency check over `lifecycle_transitions` |
| evidence_promotion_nightly     | daily 02:00 UTC    | promotes news / SOW / story rows → `evidence_index` |
| sow_full_reindex               | weekly Sun 05:00   | `sow_service.ingest_all()` w/ reindex log |
| benchmark_extrapolation_run    | weekly Mon 07:00   | `benchmarks_service.refresh(extrapolate=True)` |
| deep_audit_weekly              | weekly Mon 08:00   | `audit_service.run_audit()` + notifications refresh |
| eval_run_weekly                | weekly Mon 08:30   | `eval_service.run_eval()` |
| benchmark_recompute_quarterly  | quarterly 1st 06:00| `benchmarks_service.refresh(extrapolate=True)` |
| digest_quarterly               | quarterly 1st 09:00| `digest_service.generate()` per subvertical |

Pub/Sub topic conventions (per `services/event_bus._TOPIC_MAP`):

| Event                           | Topic              | Producers |
|---------------------------------|--------------------|-----------|
| job.completed / job.failed      | job-events         | runner    |
| audit.critical_finding          | audit-events       | deep_audit_weekly |
| lifecycle.transitioned          | lifecycle-events   | lifecycle_scoring_daily |
| digest.generated                | digest-events      | digest_quarterly |
| suggestion.applied / .rejected  | suggestion-events  | api/suggestions |

Production swap-ins (each gates on its env var):
- `USE_GCP=true` → `MongoRepository` for Firestore in MongoDB-compat mode
- `OTEL_EXPORTER_OTLP_ENDPOINT=…` → OpenTelemetry FastAPI instrumentation
- `LLM_LIVE_MODE=true` → real Anthropic + Vertex calls
- `BUILTWITH_API_KEY` / `WAPPALYZER_API_KEY` → live technographics

## Batch 8 — Operator surface (chat + what-if + personas + notifications + exports + eval)

```
POST /api/chat/messages ──▶ chat_service.post_message
                              ├── extract sub_cap_id from text (regex)
                              ├── VectorStore.search (top_k=8)  ← Batch 4
                              ├── + lifecycle_score / sow_mention rows
                              │   for the detected subcap
                              ├── consultant_loop.run(GEMINI_PRO)
                              │   with rolling history (10 turns max)
                              └── persist conversation + return citations + chain_id


POST /api/what-if/simulate ──▶ what_if_service.simulate (pure function)
                                ├── deep-copy lifecycle_scores + vendor_adoption
                                ├── apply each action:
                                │     add_sow_mention / set_lifecycle_state /
                                │     promote_vendor / add_news_mention
                                ├── recompute score + reclassify state per delta
                                └── return state_changes + adoption_changes +
                                    new_transitions diff


GET /api/personas       ──▶ personas_service.list_personas
                              └── index subcaps.personas → per-persona stats
                                  joined with lifecycle state distribution


POST /api/notifications/refresh ──▶ notifications_service.refresh
                                     ├── _from_audit (latest report findings)
                                     ├── _from_lifecycle_transitions (last 7d)
                                     └── _from_suggestions (status=pending)
                                          → notifications collection (read-flag preserved)


GET /api/exports/{file}.xlsx ──▶ exports_service.export_*
                                  ├── catalogue.xlsx (subcaps + categories)
                                  ├── lifecycle.xlsx (state + signals)
                                  ├── clients.xlsx (clients + client_subcaps)
                                  └── benchmarks.xlsx (per-cohort distributions)


POST /api/eval/run ──▶ eval_service.run_eval
                        ├── digest_priorities  (overlap@k vs golden labels)
                        ├── gate_consistency   (same prompt → same verdict)
                        └── citation_grounding (claim sources resolve)
                             → eval_runs collection
```

Pipeline notes:

- The chat service routes to `consultant_loop` so every reply inherits
  the 8-gate validation + cost ledger.
- The what-if simulator imports lifecycle's score / classify functions
  by reimplementing them on a dict shape — keeps the simulator dependency
  acyclic with `lifecycle_service`. State buckets stay in lockstep via
  shared constants and a reused decision table.
- Persona indexing is O(subcaps) with no LLM cost; the API surface
  joins lifecycle scores in-memory.
- Notifications dedupe via stable IDs (`notif-{kind}-{source-ref}`),
  so re-running refresh preserves the `read` flag.
- XLSX exports are streamed in-memory via openpyxl; no temp files
  written to disk. Brand-coloured headers (`#103D33`) match spec §14.
- Eval bootstraps a synthetic dataset for `retail-banking::2026-Q2`
  expecting `[P1C1.1.1, P1C1.1.2, P1C1.1.3]`. Drop additional JSON
  golden labels into `test-data/eval/` to extend.

## Batch 7 — Strategic digest + Deep audit + PPTX export

```
                ┌──────────────────────────────────────────────────────┐
POST /api/      │              digest_service.generate()                │
digest/         │                                                       │
generate     ──▶│  1. Resolve subvertical → vc_mappings codes (RB/WM/…) │
                │  2. Filter lifecycle_scores by subcap_ids in mapping  │
                │  3. Sort by score desc, keep RISING/STABLE/EMERGING   │
                │  4. For each priority:                                │
                │       SOW excerpts (Batch 3)                          │
                │       benchmark distributions (Batch 5)               │
                │       news + trends (Batch 4)                         │
                │  5. consultant_loop.run(model=OPUS) → narrative       │
                │  6. Q-over-Q delta vs previous_period digest          │
                │  7. Persist → strategic_digests                       │
                └────────────────────────┬──────────────────────────────┘
                                         │
                                         ▼
                            ┌─────────────────────────┐
GET /api/digest/{id}/pptx ─▶│   pptx_export.render()  │
                            │   1. title slide (logo) │
                            │   2. executive overview │
                            │   3. priority N slides  │
                            │   4. watchlist slide    │
                            │   → bytes (Microsoft    │
                            │     PowerPoint 2007+)   │
                            └─────────────────────────┘


POST /api/audit/run ──▶  audit_service.run_audit()
                          ├── _sweep_gates()       reasoning_chains: fail + low score
                          ├── _sweep_stale_…       suggestions: pending > 14d
                          ├── _sweep_dead_subcaps  lifecycle_scores: state == DEAD
                          ├── _sweep_flags         flags: status == OPEN
                          └── _sweep_cost          llm_costs: today ≥ 80% of cap
                                  ▼
                          audit_reports collection (severity-rolled findings)
```

Subvertical resolution: `digest_service._resolve_subvertical_codes()` maps
the user-facing input ("RB", "retail-banking", "Retail Banking") to the
canonical short code from `config/subverticals.yml`. The matched codes
intersect with `vc_mappings.subvertical_code` to find subcaps for that
slice.

Q-over-Q delta: `_previous_period("2026-Q2")` → `"2026-Q1"`; if a digest
exists for the previous period, each priority gets a `delta` block with
`previous_state` + `previous_score` + `previous_period`. The PPTX
priority slide and the StrategicDigest UI both render this delta as
`previous_state → current_state`.

PPTX schema:
- 16:9 widescreen, 13.333" × 7.5"
- Brand palette wired from spec §14 (`ZEN_DARK_GREEN`, `ZEN_TEAL`, etc.)
- Title slide: Zennify wordmark + tagline + period + subvertical
- Overview slide: summary + 6-KPI strip (priorities / rising / stable /
  emerging / sources / cost)
- One slide per priority: state badge (rounded rectangle, brand-coloured),
  narrative + recommendation column + evidence column
- Watchlist slide: RISING / EMERGING for next quarter

Audit findings severity rules:

| Kind              | Severity | Trigger |
|-------------------|----------|---------|
| GATE_FAIL         | critical | reasoning_chain.overall == "fail" |
| LOW_GATE_SCORE    | warn     | warn + score < 0.5 |
| STALE_SUGGESTION  | warn     | pending suggestion older than 14 days |
| DEAD_LIFECYCLE    | info     | lifecycle_scores.state == DEAD |
| OPEN_FLAGS        | warn     | flag with status OPEN |
| HIGH_COST_DAY     | warn / critical | daily LLM spend ≥ 80% / ≥ throttle_pct |

Production swap-ins (when keys land):
- Live mode + Anthropic key → real Opus narratives via the Batch 4 router.
- `BATCH7_SCHEDULE` cron (Cloud Scheduler) → weekly audit + monthly digest
  jobs (deferred to Batch 9).
- Logo upload via Settings page → drops in to PPTX title slide.

## Batch 6 — Lifecycle + Vendor Intelligence + Client Journey

```
Batch 3 SOWs + mentions + stories ─┐
Batch 4 news + trends            ─┤
Batch 5 benchmark distributions  ─┤
Batch 5 AI extrapolations        ─┘
                                  │
                                  ▼
                  lifecycle_service.recompute_all()
                  ├── _build_index()  (one pass per collection)
                  ├── _build_metric_subcap_index()
                  └── for each subcap:
                        ├── _gather_signals(idx, metric_subcap_index)
                        │   ├── SOW counts (active/prospect/inactive/archived)
                        │   ├── story velocity
                        │   ├── news + trends 90-day cadence
                        │   └── benchmark verdict mix
                        ├── _score(sig)        → 0..100, 4-component weighted
                        ├── _classify_state(sig, score)
                        │       EMERGING | RISING | STABLE | DECLINING | FADING | DEAD
                        └── append transition row if state changed
                                           │
                                           ▼
                  lifecycle_scores  +  lifecycle_transitions  +  lifecycle_runs


Batch 5 technographics → vendor_intel_service.refresh()
                            ├── per-vendor aggregates (companies, cohorts, news_mentions)
                            ├── per (vendor × cohort) adoption %
                            └── news + trends event indexing by vendor name
                                  → vendor_profiles + vendor_adoption + vendor_events


Batch 3 SOWs + Batch 6 lifecycle → client_journey_service
                                     ├── _build_journey(client_name)
                                     │     ├── SOW counts by status
                                     │     ├── touched subcaps + lifecycle state
                                     │     ├── vendor stack + cohort adoption
                                     │     └── state distribution
                                     ├── get_journey()  → JSON for UI
                                     ├── refresh_all()  → one journey per client
                                     └── dma_packet()   → flat dma-handoff-v1 schema
```

State classification rules (per spec §8):

| Score   | Recent active signal | State      |
|---------|----------------------|------------|
| ≥70     | sow_age ≤ 30d        | RISING / STABLE |
| 45-69   | any active           | RISING (if news ≥2 or prospect SOW) else STABLE |
| 20-44   | any active           | EMERGING |
| <20     | any active           | EMERGING |
| any     | only historical      | FADING (score<25) / DECLINING |
| 0       | no signal at all     | DEAD |

Performance — `Repository.defer_persist()`:

The JSON-backed `InMemoryRepository` re-serialises the whole file on every
`upsert` to keep dev simple. Hot-loop ingest (4,844 stories, 199 subcap
lifecycle scores) made that O(N²) with per-write disk flushes, blowing
through 10-minute test timeouts. Batch 6 introduces a context manager:

```python
with repo.defer_persist():
    for row in 4844_stories:
        repo.upsert("stories_canonical", row["story_key"], row)
```

The repo only flushes once on context exit. Mongo path is a no-op since
each Mongo write goes to Firestore directly. All Batch 3-6 ingest
services now wrap their hot loops.

## Batch 5 — Public benchmarks + technographics + AI extrapolation

```
test-data/filings/*.json          (live: SEC EDGAR REST + FDIC Call Report)
test-data/analyst-reports/*.json  (live: doc-AI parsed Drive PDFs, license-gated)
test-data/technographics/*.json   (live: BuiltWith / Wappalyzer / Similartech)
        │
        ▼
benchmarks_service.refresh()
        │
        ├── normalize each row → benchmark_observations
        ├── classify company against config/peer_cohorts.yml
        │       (subvertical × asset-size bucket × business model)
        ├── group (metric, cohort, period) → distribution
        ├── compute n / min / max / mean / stdev / p25 / p50 / p75 / cv
        ├── if N < 3 in any cohort: consultant_loop.run()
        │   → AI-extrapolated obs (tier T5, is_extrapolated=true, chain_id)
        ├── assign verdict: BENCHMARK | INDICATIVE | EXPLORATORY
        └── persist to benchmark_distributions + benchmark_sources
                                    │
                                    ▼
                       Benchmarks Studio page
                  (filter by metric × cohort × subcap)
```

Verdict thresholds (per spec §7):

| Verdict       | Rule                                                          |
|---------------|---------------------------------------------------------------|
| `BENCHMARK`   | N ≥ 5, source_kinds ⊆ {filing, analyst}, coef_var ≤ 0.3      |
| `INDICATIVE`  | N = 3-4 OR mixed sources OR moderate variance                |
| `EXPLORATORY` | N < 3 OR includes any `is_extrapolated=true` observation     |

Subcap-aware filter: each metric in `config/benchmark_metrics.yml` has a
`subcap_mappings` list of glob patterns (e.g. `P1C2.3.*`).  The
`/api/benchmarks?sub_cap_id=P1C2.3.5` query expands those patterns to
return all metrics whose mapping covers the subcap.

AI extrapolation routes through the Batch-4 consultant loop with
`ModelKind.GEMINI_PRO`, persists a `chain_id` on the observation, and
links back to the Reasoning Chain Viewer for full audit trail.  The 8
gates run on each extrapolation; the resulting observation is tagged
EXPLORATORY whether or not the gate verdict is `pass`.

Production swaps (when keys + legal sign-off land):
- SEC EDGAR REST: `https://data.sec.gov/submissions/CIK{cik}.json` +
  `https://data.sec.gov/api/xbrl/companyconcept/...` — requires a
  `User-Agent` with the value of `SEC_EDGAR_EMAIL`.
- FDIC Call Report: `https://banks.data.fdic.gov/api/financials` (REST).
- Analyst PDFs: doc-AI on a Drive folder, gated on `LEGAL_SIGNOFF=true`.
- BuiltWith / Wappalyzer: REST APIs gated on `BUILTWITH_API_KEY` /
  `WAPPALYZER_API_KEY`; without keys, the engine reads the seed JSONs.

## Batch 4 — LLM core + reasoning + gates

```
                    ┌─────────────────────────────────────────────┐
api/reasoning-      │            7-step consultant loop            │
chains/run    ─────▶│  clarify → retrieve_internal → retrieve_ext │
                    │  → synthesize → adversarial → propose       │
                    │  → gate → finalize                          │
                    └────────────┬────────────────────────────────┘
                                 │
        ┌────────────────────────┼─────────────────────────┐
        │                        │                         │
        ▼                        ▼                         ▼
  llm/router.call()     services/news_service          services/validation_gates
  ├── _call_dev (free)  ├── local seed → test-data/   ├── schema   ├── novelty
  ├── _call_anthropic   ├── RSS via feedparser (live) ├── citation ├── bias
  └── _call_vertex      └── auto-tag subcap mentions  ├── halluc.  ├── breaking
                              + index in VectorStore   ├── fresh.  └── peer-cov
                                                       │
                                       ┌───────────────┘
                                       ▼
                              services/hallucination
                              services/citation_verifier
                                       │
                                       ▼
                            reasoning_chains + suggestions collections
                                       │
                                       ▼
                  Reasoning Chain Viewer / AI Suggestions pages
```

Routing matrix (per spec §3 / ADR-0004) — re-confirmed in Batch 4:

| Model         | Use case                                  | Pricing/M (blended) |
|---------------|-------------------------------------------|---------------------|
| `gemini-flash`| Claim extraction, first-pass adversarial  | $0.30               |
| `gemini-pro`  | Mid-cost synthesis, multi-step reasoning  | $3.50               |
| `sonnet`      | High-quality reasoning, suggestions, critic | $6.00             |
| `opus`        | Quarterly digest + breaking-change adjudication | $30.00        |

Dev-mode behavior: when `Settings.llm_live_mode=False`, every adapter
resolves to `_call_dev` which returns deterministic canned JSON keyed off
the prompt's source IDs and the requested subcap.  Tests + the entire UI
flow run end-to-end without any API keys, and the gate engine evaluates
the canned response just like a real one.  Switching to live mode is a
single-flag flip; no consumer code changes.

Cost guardrails (`services/llm/cost_tracker.py`) read every adapter call
into the `llm_costs` collection.  `assert_within_budget()` runs before
every router call; raises `BudgetExceeded` once daily / weekly thresholds
hit `cost_throttle_pct` (default 90%).  The `validation-gates/summary`
endpoint surfaces today + 7-day spend per model.

Cache (`services/llm/cache.py`) is keyed on
SHA256(model + system + prompt + temperature + max_tokens).  Cached hits
return ``cached=True, cost_usd=0`` so the budget is unaffected.  Soft-LRU
eviction kicks in once `LlmCache.max_entries` (default 5,000) is reached.

The 8-gate engine is a pure function over `(output, sources)`; the loop
calls it once and persists the results inside the `reasoning_chains`
document.  Suggestions are queued with the gate verdict so reviewers can
filter on the AI Suggestions page (e.g. "show only `pass`" before bulk-
applying).

Production swaps (when keys land):
- `LLM_LIVE_MODE=true` activates Anthropic + Vertex adapters.
- `ANTHROPIC_API_KEY`, `GCP_PROJECT_ID`, `VERTEX_REGION` resolve as
  Pydantic-Settings env reads.
- Model IDs are pinned via Settings (`anthropic_model_sonnet`, …) so
  upgrade is a one-line change in `.env`.
- Live news/trends activates when `news_feeds` is non-empty.

## Batch 3 — Internal evidence

```
Drive folder (status subfolders)              local mode: test-data/SOWs/
   └── sow_service.discover_sows()
        └── _read_bytes()
             └── text_extraction.extract()    [pypdf | python-docx | txt]
                  └── dlp_service.redact()    [regex; Cloud DLP swap-in]
                       └── chunk_text()        [paragraph-aware ~1200ch w/ 100 overlap]
                            ├── extract_mentions()  [exact_id + name_substring + name_fuzzy]
                            └── guess_client()      [entity_resolver: alias + WRatio]
                                 └── persist sows / sow_chunks / sow_mentions / clients
                                      └── /api/sows/{...} + /api/projects/subcap-trace

gen_stories_export.xlsx                       local: test-data/gen_stories_export.xlsx
   └── stories_service.ingest_canonical()
        └── stories_canonical collection (4844 in Pillar 1)

Atlassian Cloud (when JIRA_BASE_URL + creds)
   └── stories_service.ingest_jira()
        └── jira_stories collection
```

The Repository abstraction from Batch 1 absorbs all collection writes. The
Subcap Deep Dive `/api/catalogue/subcaps/{id}` response now joins
sow_mentions + stories_canonical + jira_stories in addition to the
spine/maturity/themes Batch-1 fields.

Mention extraction is conservative on purpose for Batch 3: exact ID match
(99 confidence), case-insensitive substring on subcap name (85), and
WRatio token-set ≥92 fallback. Batch 4's LLM router wraps the same chunker
output and pushes higher-fidelity claim extraction through Gemini Flash
into the same `sow_mentions` collection.

Production swaps (when GCP creds land):
- Drive list/download: `drive_service._discover_drive` already exists in
  `sow_service._discover_drive`, gated on `s.use_gcp + s.drive_sows_folder_id`.
- Document AI: `text_extraction.extract` switches on `Settings.use_gcp`
  and a configured DocAI processor — same return shape (`ExtractedDocument`).
- Cloud DLP: `dlp_service.redact` switches on the same flag — same return
  shape (`RedactionResult`).

## Batch 2 — Knowledge Graph + lenses

```
catalogue_service (Batch 1 collections)
  └── graph_service.build_graph()  [NetworkX MultiDiGraph, LRU(8) by ingest_run_id]
        ├── reads pillars / categories / l1 / subcaps / use_cases / l3 / l4 /
        │   maturity / themes / vc_mappings
        ├── reads config: subverticals.yml, vcc_clusters.yml, uc_tag_families.yml
        └── emits 14 node kinds + 13 edge kinds
              ├── /api/graph/{summary, elements, neighborhood/{id}, path,
              │              centrality, communities, impact/{id}}
              └── /api/lens/{subverticals, clusters, uc-tag-families,
                            value-chain-atlas, subvertical-compare/{id},
                            maturity-heatmap, use-case-explorer, platform-catalog}
```

VC stage classification: cells in 21_VC_Mapping_PerSubcap are encoded as
`▌ STAGE A\n▌ STAGE B`. The parser splits on `▌`; the graph_service heuristic
classifier matches each stage label against keyword lists in vcc_clusters.yml
(first match wins) to assign one of VCC-01..08, falling to VCC-00 for unmatched.

Cache invalidation: catalogue_service._run_ingest() calls
graph_service.invalidate_cache() at end-of-run so the next /api/graph/* call
rebuilds from the new snapshot.

## Batch 1 — Catalogue spine

```
Drive folder (subfolders per pillar)
   └── auto-pick latest non-inactive .xlsx per pillar (drive_service)
        └── openpyxl parser (sheets_parser) → ParseResult
             └── catalogue_service.refresh_pillar / refresh_all_pillars
                  ├── Repository (pymongo on Firestore-MongoDB OR in-memory)
                  │     ├── pillars / categories / l1_capabilities / subcaps
                  │     ├── use_cases / l3_platforms / l4_features
                  │     ├── maturity_descriptors / theme_mappings / stories
                  │     └── ingest_runs / flags
                  ├── version_service.save_version → snapshot + version doc
                  └── change flags raised on schema-incomplete / ingest failures
```

The Repository abstraction is intentionally narrow (CRUD + bulk + distinct).
Domain logic stays in the services that compose it. In dev/tests the
in-memory implementation persists to a JSON file (`local_repository_path`)
so multi-request flows behave like a real DB.

`pymongo` 4.9.x is pinned because Firestore in MongoDB-compatibility mode
speaks a wire protocol compatible with that range. Connection string:

```
mongodb://<sa_email>:<token>@<host>:443/dma-assessor?authMechanism=MONGODB-OIDC&loadBalanced=true&tls=true
```

## Batch 0 ADRs

### ADR-0001 — Drop graph-tool

`graph-tool` requires a Debian build chain that doesn't fit `python:3.12-slim`.
NetworkX + BigQuery `GRAPH_TABLE` covers ≤2K-node interactive graphs and
≥5K-node analytical queries respectively. Sigma+WebGL on the frontend handles
large render. Decision is reversible later by switching the runtime base image.

### ADR-0002 — SPA bundled in API container

The spec says "single Cloud Run service for HTTP". The Vite-built SPA is
bundled into the Python image and served as static. Pros: one deploy, simple
auth domain, simpler CORS. Cons: cold-start ~2-3s. Revisit in Batch 9 if
we want CDN-fronted static frontend.

### ADR-0003 — Dev-mode auth bypass

`AUTH_MODE=dev` accepts `Bearer dev-<email>` (domain-restricted). This lets
pytest / Playwright / docker-compose run with no Firebase project. In `firebase`
mode, the verifier path uses the Firebase Admin SDK (wired Batch 1).

### ADR-0004 — Pinned model IDs

The spec names "Claude Sonnet 4" and "Claude Opus 4.7"; latest available IDs
matching the spec's intent are `claude-sonnet-4-6` and `claude-opus-4-7`.
Embedding model defaults to `text-embedding-005` (768d). Gemini IDs:
`gemini-2.5-flash` / `gemini-2.5-pro`. Reconfirmed in Batch 4.

### ADR-0005 — Firestore in MongoDB-compatibility mode

User chose MongoDB compatibility for the `dma-assessor` Firestore database.
We use `pymongo` (sync) for Batch 1; `motor` for async wraps in later batches
will require pinning to a compatible pymongo (4.9.x) to avoid the resolver
conflict we hit during build. The repository abstraction means this choice
is reversible — a future `FirestoreNativeRepository` can be added without
touching domain code.

### ADR-0006 — Drive auto-discovery rules

Per-pillar subfolder scan; exclude any filename containing `inactive`
(case-insensitive); pick the highest semver-ish `v<x>.<y>` token; fallback
to most-recent `modifiedTime`. Schema-mismatched workbooks (missing the
required headers in `2_Capability_Map`) are still tracked with a
`SCHEMA_INCOMPLETE` flag and visible on Mission Control, so users see when
Pillar 2-4 files arrive that don't yet match Pillar 1's structure.
