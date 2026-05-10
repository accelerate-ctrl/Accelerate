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

## Firestore collections — Batch 9

| Collection | Doc ID | Description |
|---|---|---|
| `evidence_index` | `{kind}-{source-id}` | Promoted canonical evidence (news / sow / story) |

(All 14 Cloud Run Jobs write into existing collections defined by their
respective services; the only new collection in Batch 9 is
`evidence_index`, populated by `evidence_promotion_nightly`.)

## Firestore collections — Batch 8

| Collection | Doc ID | Description |
|---|---|---|
| `chat_conversations` | `chat-{hex12}` | RAG chat session: rolling turns + per-turn citations + chain_id |
| `notifications` | `notif-{kind}-{ref}` | In-app notifications w/ severity + read flag + back-ref |
| `notification_runs` | `notif-refresh-{micro-ts}` | Per-refresh summary |
| `eval_runs` | `eval-{dataset}-{micro-ts}` | Per-eval-run results: cases + pass rate + mean score |
| `eval_datasets` | dataset_id | Persisted golden datasets (seeds always re-derived from disk) |

## Firestore collections — Batch 7

| Collection | Doc ID | Description |
|---|---|---|
| `strategic_digests` | `digest-{subvertical-slug}-{period}` | Quarterly digest with priorities + narratives + evidence + Q-over-Q delta |
| `digest_runs` | `digest-run-{unix}` | Per-generation run log |
| `audit_reports` | `audit-{micro-ts}` | Per-audit findings + severity rollup + inputs_seen |

## Firestore collections — Batch 6

| Collection | Doc ID | Description |
|---|---|---|
| `lifecycle_scores` | sub_cap_id | Per-subcap state + score + signals + last_signal_at |
| `lifecycle_transitions` | `trans-{sub_cap_id}-{ts}` | Append-only state-change log |
| `lifecycle_runs` | `lifecycle-{unix}` | Per-recompute summary (state distribution, transitions) |
| `vendor_profiles` | vendor_id (slug) | Companies, cohorts, news_mentions, ai_signal_avg |
| `vendor_adoption` | `adop-{vendor}-{cohort}` | Per (vendor × cohort) adoption % + adopters list |
| `vendor_events` | `evt-{vendor}-{news_id}` | Vendor-tagged news / trend rows |
| `vendor_intel_runs` | `vendor-intel-{unix}` | Per-refresh run log |
| `client_journeys` | client slug | Per-client synthesis: SOWs + touched subcaps + vendor stack |

## Firestore collections — Batch 5

| Collection | Doc ID | Description |
|---|---|---|
| `benchmark_observations` | `obs-{kind}-…` | One row per (company, metric, period); filing / analyst / technographic / ai_extrapolation |
| `benchmark_distributions` | `dist-{metric}-{cohort}-{period}` | n + percentiles + verdict per cohort × metric × period |
| `benchmark_cohorts` | cohort_id | Cohort metadata loaded from `peer_cohorts.yml` |
| `benchmark_sources` | `src-{label}` | Aggregated source catalogue (label, tier, kind, observation_count) |
| `benchmarks_ingest_runs` | `benchmarks-ingest-{unix}` | Per-refresh run log |

## Firestore collections — Batch 4

| Collection | Doc ID | Description |
|---|---|---|
| `llm_cache` | sha256 of (model+system+prompt+temp+max_tokens) | Cached LLM completions; soft-LRU eviction by `hit_at` |
| `llm_costs` | `cost-{us-ts}-{model}` | Per-call cost ledger; daily + weekly budget rolls up here |
| `vector_index` | doc_id | 256-dim embedding + text + metadata for similarity search |
| `news_items` | sha-prefixed news id | News rows w/ `sub_cap_hits` |
| `trends_items` | sha-prefixed trend id | Trends rows |
| `news_ingest_runs` | `news-ingest-{unix}` | Ingest run log |
| `reasoning_chains` | `chain-<hex12>` | 7-step loop trace: steps, sources, claims, gates, suggestions |
| `suggestions` | `sug-<chain_id>-<n>` | Staged catalogue edits w/ status pending/applied/rejected |
| `suggestion_applies` | `apply-<sug_id>` | Apply transitions (queued for diff in Batch 6) |
| `citation_probes` | sha256 of url | URL HEAD probe results, 24h TTL |

## Firestore collections — Batch 3

| Collection | Doc ID | Description |
|---|---|---|
| `sows` | `sow-{status}-{slug}` | One per ingested SOW with provenance, client, redaction summary |
| `sow_chunks` | `{sow_id}-c{NNNN}` | Paragraph-aware chunks of redacted text |
| `sow_mentions` | `{sow_id}-m{NNNN}` | Subcap mentions with method + confidence + excerpt |
| `sow_ingest_runs` | `sow-ingest-{unix}` | Per-refresh run log |
| `clients` | canonical client name | Aggregated client record (sow_count, statuses[], first_seen, last_seen) |
| `stories_canonical` | `story_key` | gen_stories_export rows with quality scores |
| `jira_stories` | Jira issue key | Live Atlassian issues |
| `stories_ingest_runs` | `stories-ingest-{unix}` | Canonical + Jira ingest run log |

## Knowledge graph — Batch 2

| Node kind | Source | Notes |
|---|---|---|
| `Pillar` | `pillars` collection | P1..P4 |
| `Category` | `categories` | e.g. P1C1..P1C4 |
| `L1_Capability` | `l1_capabilities` | synthesized per subcap row |
| `Subcap` | `subcaps` | 199 in Pillar 1 |
| `UseCase` | `use_cases` | 827 in Pillar 1 |
| `UC_Tag` | extracted from UC labels | 22 archetype tags |
| `L3_Platform` | `l3_platforms` (+ subcap references) | 45 in Pillar 1 |
| `L4_Feature` | `l4_features` | 1,852 in Pillar 1 |
| `Theme` | `theme_mappings` | 8 cross-pillar themes |
| `MaturityDescriptor` | `maturity_descriptors` × M1..M5 | 796 nodes (199 × ~4 filled levels) |
| `Subvertical` | `subverticals.yml` | 10 nodes |
| `Cluster` | `vcc_clusters.yml` | 8 universal + VCC-00 unclassified |
| `VC_Stage` | `vc_mappings` | distinct (subvertical, stage) pairs |
| `Persona` | `subcaps.personas` | distinct persona strings |

| Edge kind | From → To | Notes |
|---|---|---|
| `BELONGS_TO` | Subcap→Category, L1→Category, Category→Pillar | hierarchy |
| `USES_PLATFORM` | Subcap → L3_Platform | bracketed L3 ID match |
| `USES_FEATURE` | Subcap → L4_Feature | composition |
| `DELIVERED_BY` | L4_Feature → L3_Platform | composition |
| `SUPPORTS_UC` | Subcap → UseCase | use case mapping |
| `TAGGED_AS` | UseCase → UC_Tag | archetype tag |
| `REFERENCES_THEME` | Subcap → Theme | cross-pillar theme |
| `HAS_MATURITY` | Subcap → MaturityDescriptor | per-level descriptor |
| `MAPS_TO_STAGE` | Subcap → VC_Stage | subvertical-specific |
| `IN_CLUSTER` | VC_Stage → Cluster | universal classification |
| `IN_SUBVERTICAL` | VC_Stage → Subvertical | per-subvertical scoping |
| `APPLIES_TO` | Subcap → Subvertical | aggregate applicability |
| `CONSUMED_BY` | Subcap → Persona | persona ownership |

Graph total at Pillar 1 v14.0: **4,014 nodes / 12,249 edges**.

Remaining 14 node kinds (Story / SOW / Project / Client / Vendor / Regulator /
Filing / NewsItem / ResearchReport / Benchmark / PeerCohort /
RegulatoryRequirement / EvidenceItem / CapabilityGap) and the 30+ remaining
edge kinds light up in Batches 3-6.

## Prompts — Batch 4+

`backend/app/agents/prompts/` is the source of truth. Each prompt is
versioned (`<name>.v<n>.md`). Eval-harness regression on prompt edits is
enforced from Batch 8.
