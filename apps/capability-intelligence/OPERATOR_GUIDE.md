# Operator Guide

> Filled in batch-by-batch as features ship.

## TOC

1. Sign-in — Batch 1
2. Configure sources — Batch 1
3. Pull all sources — Batch 1
4. Save a catalogue version — Batch 1
5. Diff two versions and read the narrative — Batch 1
6. Review change flags — Batch 1
7. Review AI suggestions — Batch 4
8. Read a benchmark distribution + adversary verdict — Batch 5
9. Move a subcap through lifecycle — Batch 6
10. Export a client journey for the DMA App — Batch 6
11. Read the Quarterly Strategic Digest — Batch 7
12. Switch persona — Batch 8
13. Run a What-If simulation — Batch 8

## 1. Sign in

In dev: requests use `Authorization: Bearer dev-<email>` where the email must
end in the configured `AUTH_ALLOWED_DOMAIN` (default `zennify.com`). The web
client wires this automatically; pytest sends it via the `auth_headers`
fixture. Production sign-in (Batch 9) is Firebase Google sign-in restricted
to the same domain.

## 2. Configure sources

After running `scripts/setup.sh`, share the Drive pillars folder
(`1rF9zdx1qF7BJ9t21eFdvZQW11Y5dUjy3` or your own) with the printed service
account email. Confirm in **Settings** that the folder ID and project are
populated. For local dev, set `LOCAL_CATALOGUE_DIR=apps/capability-intelligence/test-data`
to point at the bundled Pillar 1 file.

## 3. Pull all sources

In **Mission Control**, click **Refresh all** in the "Pillar source files"
panel. Each pillar gets re-discovered (latest non-inactive version), parsed,
and persisted. Per-pillar refresh is also available alongside each row.

## 4. Save a catalogue version

Open **Version Timeline**, fill optional label/summary, click **Save
version**. The current state of every subcap and pillar is snapshotted; the
new version becomes "current".

## 5. Diff two versions

**Diff Viewer** lets you pick A and B from the version dropdowns. The grid
shows added / removed / modified subcaps with field-level changes plus
pillar-count deltas and category deltas. Narrative explanation lands in
Batch 4 (Gemini 2.5 Pro).

## 6. Review change flags

**Change Flags Inbox** lists open flags (mapping regressions, theme
alignment, schema-incomplete pillars, ingest failures). Each shows
severity, kind, target, detail, and a Resolve button.

## 7. Explore the Knowledge Graph (Batch 2)

**Knowledge Graph** page renders the catalogue as a Cytoscape graph. Use the
node-kind filter row to add/remove kinds; the max-nodes slider keeps the
layout responsive. Click a node to select; click a Subcap-kind node to jump
to its Subcap Deep Dive. The right panel ranks nodes by degree / pagerank /
betweenness centrality. Communities, paths, and impact-analysis are also
exposed at `/api/graph/*` and surface in richer UI alongside the Reasoning
Chain Viewer in Batch 4.

## 8. Read the Value Chain Atlas (Batch 2)

**Value Chain Atlas** groups the universal 8 VCC clusters and lists the
subvertical-specific stages classified into each. Use the subvertical
selector to filter to one of the 10 subverticals. Stages that don't match
any cluster keyword fall to VCC-00 — these are flagged for human review.

## 9. Compare across subverticals (Batch 2)

**Subvertical Compare** picks one subcap and shows how it manifests across
all 10 subverticals: which subverticals it applies to and which stages cover
it. The page is keyed off the subcap dropdown; deep-link via `?id=<sub_cap_id>`.

## 10. Inspect maturity, use cases, and platforms (Batch 2)

- **Maturity Heatmap**: 199 × M1..M5 with cell shading by descriptor depth.
- **Use Case Explorer**: 22 archetype tags grouped into 5 families with
  per-tag counts and sample drilldown.
- **Platform Catalog**: 45 L3 platforms grouped by vendor with subcap-usage
  counts and reference-doc links.

## 11. Ingest SOWs (Batch 3)

In production, drop SOWs into the configured Drive shared-drive under one
of the four status subfolders: `active/`, `prospect/`, `inactive/`,
`archived/`. Local dev: drop them into
`apps/capability-intelligence/test-data/SOWs/<status>/`. Click **Refresh
ingest** on the SOW Library page to scan; ingestion does:

1. Text extraction (pypdf for `.pdf`, python-docx for `.docx`, raw read
   for `.txt`/`.md`)
2. PII redaction (regex SSN/email/phone/credit-card; Cloud DLP in prod)
3. Paragraph-aware chunking (~1200 chars, 100 overlap)
4. Subcap mention extraction (exact ID + name match + WRatio fuzzy)
5. Client canonicalization via entity_aliases.yml + WRatio

Each SOW row shows redaction summary, mention count, and a *Show preview*
toggle that renders the redacted text + per-subcap mentions with excerpts.

## 12. Ingest stories (Batch 3)

Story Library → **Refresh** runs:
- Canonical: parses `gen_stories_export.xlsx` (4,844 rows in Pillar 1) into
  `stories_canonical` with all quality scores
- Live Jira: pulls projects listed in `JIRA_PROJECT_KEYS` via
  `atlassian-python-api`. Skipped cleanly if Atlassian creds aren't set.

The page shows canonical on the left (with composite/AC/SD/delivery/
confidence scores) and live Jira on the right.

## 13. Trace a subcap to projects (Batch 3)

**Project–Subcap Trace** picks one subcap → renders a vertical timeline of
every SOW mention + every story (canonical + Jira), newest first. Each
event shows the client, status, method (exact_id / name_substring /
name_fuzzy), confidence, and excerpt.

## 14. Refresh news + trends (Batch 4)

**News Watch → Refresh** runs `news_service.refresh()`:
- Loads JSON seed files from `test-data/news/` and `test-data/trends/`
  (one record per file or list per file).
- In live mode, also pulls every URL in `Settings.news_feeds` via
  `feedparser` (any failure is reported in `schema_issues`).
- Auto-tags each item with subcap mentions using the same extractor as
  Batch 3 (exact ID + name substring + token-set fuzzy).
- Indexes every item into the `vector_index` collection so the consultant
  loop's external-retrieval step finds it by semantic match.

The Trends Monitor page shares the same ingest run.

## 15. Trigger a 7-step consultant loop (Batch 4)

**Reasoning Chain Viewer → Run loop** with a query, optional subcap, and
model choice (`gemini-flash` for cheap claim extraction, `gemini-pro` for
mid-cost synthesis, `sonnet` for high-quality reasoning, `opus` for the
quarterly digest only).  The loop:

1. **clarify**: pin scope (subcap, sub_vertical).
2. **retrieve_internal**: SOWs + canonical/Jira stories + KG vector hits.
3. **retrieve_external**: news + trends, sorted by recency.
4. **synthesize**: LLM produces JSON `{"claims": [...]}` grounded in cited evidence.
5. **adversarial**: a Sonnet-class red-teamer scores the claims (warns if weak).
6. **propose_suggestions**: catalogue-edit candidates (`add_use_case`, `refine_subcap`, …).
7. **gate**: 8 gates run; overall pass/warn/fail recorded.
8. **finalize**: chain + suggestions persisted; UI surfaces both.

Every step records model, tokens, $ cost, and cache state.  The
Validation Gates Log aggregates per-gate verdicts + cost across runs.

In dev (default), `LLM_LIVE_MODE=false` returns deterministic canned
responses keyed off the prompt; cost is $0.  Set `LLM_LIVE_MODE=true`
plus `ANTHROPIC_API_KEY` (and either Vertex creds or a GCP project) to
flip to real models.  Cost ceilings (`DAILY_SPEND_CEILING_USD`,
`ANTHROPIC_WEEKLY_BUDGET_USD`) auto-throttle calls at
`COST_THROTTLE_PCT` (default 90%).

## 16. Apply or reject a staged AI suggestion (Batch 4)

**AI Suggestions** lists every suggestion produced by the loop.  Filter by
status (pending / applied / rejected); each row links back to its
reasoning chain, gate verdict, and target subcap.  Apply queues a diff
for the catalogue version-service; reject records the actor + reason.

(Steps 17+ ship in later batches per the TOC above.)
