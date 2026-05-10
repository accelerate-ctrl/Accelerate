# Prompt versions

This directory will hold versioned prompt templates per agent role. Populated in Batch 4+.

| dir | role | model | introduced |
|---|---|---|---|
| `extraction/` | high-volume classification & extraction | Gemini 2.5 Flash | Batch 4 |
| `reasoning/` | mid-complexity reasoning | Gemini 2.5 Pro | Batch 4 |
| `adversarial/` | devil's-advocate critic | Claude Sonnet 4.6 | Batch 4 |
| `digest/` | quarterly synthesis | Claude Opus 4.7 | Batch 7 |
| `deep_audit/` | weekly catalogue audit | Claude Opus 4.7 | Batch 7 |

Every prompt is `<name>.v<n>.md`. Eval-harness regression on prompt edits is enforced from Batch 8.
