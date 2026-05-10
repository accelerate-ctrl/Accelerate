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
