# Cost Guide

> Filled in Batch 4. Locked routing matrix per spec §3.

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

Every LLM call cached by `(model, prompt_hash, input_hash)` with content-typed
TTL. Target hit rate >40%; alert <20%. (Wired in Batch 4.)

## Auto-throttling

At 80% of daily ceiling: alert. At 90%: throttle non-essential operations
(lifecycle scoring, news polling); banner in UI. Configured in Batch 4.

## Anthropic weekly budget

If 7-day rolling Claude spend exceeds `ANTHROPIC_WEEKLY_BUDGET_USD`,
`MEDIUM`-leverage tasks (currently routed to Sonnet) auto-route to Gemini 2.5
Pro and the UI shows a "degraded reasoning" banner.
