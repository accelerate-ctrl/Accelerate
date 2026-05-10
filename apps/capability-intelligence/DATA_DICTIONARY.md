# Data Dictionary

> Filled in batch-by-batch. Every Firestore collection, every BigQuery table,
> every KG node/edge type, every metric, every prompt is documented here.

## Conventions

- IDs use `<pillar>C<category>.<l1>.<subcap>` for subcaps, e.g. `P1C1.1.1`.
- ULIDs for everything else (`run_id`, `version_id`, `evidence_id`, …).
- Timestamps in ISO-8601 UTC.
- Source tiers: `T1` (regulators / official partner platform) … `T5` (vendor
  marketing).
- Claim labels: `FACT` | `INFERENCE` | `HYPOTHESIS` | `CEILING_ESTIMATE`.

## Firestore collections — Batch 1

| Collection | Doc ID | Description |
|---|---|---|
| `pillars` | `pillar_id` (`P1`..`P4`) | Pillar metadata + ingestion provenance (source file id, modified-at, version, schema status) |
| `categories` | `category_id` (e.g. `P1C1`) | Category nodes |
| `l1_capabilities` | synthesized `<category_id>.<l1_slug>` | L1 capability nodes |
| `subcaps` | `sub_cap_id` (`P1C1.1.1`) | Subcap nodes — full row from `2_Capability_Map` |
| `use_cases` | `use_case_id` (`P1C1.1.1.UC1`) | Parsed from the Use_Cases column |
| `l3_platforms` | `l3_id` (`L3-SF-FSC`) | Platforms from `4_L3_Detailed`; tagged `source_pillar_id` |
| `l4_features` | `<sub_cap>::<l3>::<feature>` | Features from `5_L4_Detailed_Features` |
| `maturity_descriptors` | `sub_cap_id` | M1..M5 descriptors from `6_Maturity_Descriptors` |
| `theme_mappings` | `<theme>::<sub_cap_id>` | Cross-pillar theme links from `15_Theme_SubCap_Mapping` |
| `stories` | `story_key` | Stories from `3_User_Stories_Catalogue` |
| `ingest_runs` | `ingest-<unix>` | One per refresh run; counts + flags |
| `flags` | `flag-<kind>-<target>-<unix>` | Open + resolved change flags |
| `catalogue_versions` | `v-<unix>` | Catalogue version metadata |
| `catalogue_snapshots` | `v-<unix>` | Embedded snapshot blob (in-memory mode) or pointer (Mongo mode) |
| `settings` | (singleton) | Editable runtime config (Batch 8) |

## BigQuery datasets — Batch 1+

| Dataset | Purpose | Activated |
|---|---|---|
| `capability_catalogue` | catalogue mirror (subcaps, l1, categories, pillars, …) | Batch 1 |
| `continuous_validation` | validation gate runs, flag history | Batch 4 |
| `benchmarks` | benchmark observations + cohorts + distributions | Batch 5 |
| `lifecycle` | lifecycle scores + transitions | Batch 6 |
| `vendor_intel` | vendor events + competitive signals | Batch 6 |
| `evals` | golden datasets + run scores | Batch 8 |
| `evidence_index` | canonical evidence with ERS, claim_label, tier, recency | Batch 4 |
| `reasoning_chains` | decomposed steps for analysis | Batch 4 |
| `cost_tracking` | token usage by model, service, day | Batch 4 |

## Knowledge graph — Batch 2+

28 node types and 50+ edge types per spec §8. Documented as nodes/edges land.

## Prompts — Batch 4+

`backend/app/agents/prompts/` is the source of truth. Each prompt is
versioned (`<name>.v<n>.md`). Eval-harness regression on prompt edits is
enforced from Batch 8.
