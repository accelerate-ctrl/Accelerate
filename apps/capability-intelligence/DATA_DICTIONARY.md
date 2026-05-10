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

## Firestore collections — Batch 1+

(populated batch-by-batch)

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
