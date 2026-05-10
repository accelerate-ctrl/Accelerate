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
