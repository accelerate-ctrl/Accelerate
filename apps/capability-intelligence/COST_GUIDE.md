# Cost Guide

> Active as of Batch 4. The router (`services/llm/router.py`), cache
> (`services/llm/cache.py`), and tracker (`services/llm/cost_tracker.py`)
> implement the policies below. The Validation Gates Log surfaces today +
> 7-day spend per model.

## Per-task model routing (locked, Batch 4)

| Task family | Model | Why |
|---|---|---|
| Embeddings | `text-embedding-005` | Cheap, no reasoning |
| Bulk extraction / classification | `gemini-2.5-flash` | Long-context + cheap |
| Mid-complexity reasoning | `gemini-2.5-pro` | Workhorse |
| Adversarial critique | `claude-sonnet-4-6` | Independent model = independent reasoning |
| Quarterly strategic digest | `claude-opus-4-7` | Highest-leverage consultant output |
| Deep audit (weekly) | `claude-opus-4-7` | One-shot, big context, high stakes |

## Daily token budgets (alerts at 80%)

| Model | Input / day | Output / day |
|---|---|---|
| Gemini 2.5 Flash | 500M | 50M |
| Gemini 2.5 Pro | 50M | 5M |
| Vertex Embeddings | 100M | n/a |
| Claude Sonnet | 3M | 500K |
| Claude Opus | 300K | 60K |

## Caching

Every LLM call is cached by SHA256(`model + system + prompt + temperature
+ max_tokens`).  Cache hits return `cost_usd=0` and `cached=true` so the
budget is unaffected.  Soft-LRU eviction kicks in once the cache exceeds
`LlmCache.max_entries` (default 5,000).  Target hit rate >40%.

## Auto-throttling

`assert_within_budget()` runs before every router call:

- At `cost_throttle_pct` of `daily_spend_ceiling_usd` (default 90%): the
  router raises `BudgetExceeded` and the API returns 429.
- At `cost_throttle_pct` of `anthropic_weekly_budget_usd`: ditto, with a
  message indicating Anthropic should be auto-routed to Gemini until reset.

Both ceilings default to `0` (disabled) — set them in `.env` to activate.

## Anthropic weekly budget

If 7-day rolling Claude spend exceeds `ANTHROPIC_WEEKLY_BUDGET_USD`,
`MEDIUM`-leverage tasks (currently routed to Sonnet) auto-route to Gemini 2.5
Pro and the UI shows a "degraded reasoning" banner.

## Quarterly digest cost (Batch 7)

Per spec §3, the quarterly digest is the single highest-leverage task
in the system. It's the only path that calls **Claude Opus** in the
default routing matrix. Each digest invokes one consultant-loop run per
priority (5 by default), so a typical generation = 5 × Opus call.

Budget guidance:
- Cap `priority_limit` at 5 to bound per-digest spend.
- Generate at most 1 digest per (subvertical × quarter) — 10
  subverticals × 4 quarters = 40 generations / year (~$80-200 expected
  in live mode).
- Audit reports are deterministic — no LLM cost.
- PPTX rendering is local — no LLM cost.

The Validation Gates Log (`/api/validation-gates/summary`) surfaces
Opus calls in the per-model breakdown so operators can see digest
spend in isolation.
