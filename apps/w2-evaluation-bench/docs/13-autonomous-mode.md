# Autonomous mode — the app scores on its own

Runs created with **Judging: Autonomous** complete with **zero external
judges**: no Claude sign-in, no Gemini key, no runner installed anywhere.
The server executes every packet in-process with two deterministic
screeners built on the pre-intelligence layer.

## What it honestly is

**Screening, not judgment.** The screeners recognize term-level evidence
(synonym-expanded, plural-folded, IDF-ranked) against the calibration
language: they verify that the SDD *names and locates* the expected depth,
with verbatim anchors that pass the same R25 validation as any judge. They
cannot weigh whether a design is *good* — that remains the AI panel's job.
Every surface discloses the mode: `evaluator_model=autonomous` in the run
record, `engine=auto-screener` on all packet usage, and an AUTONOMOUS
SCREENING MODE caveat in the report's confidence section.

## How the two slots differ (real divergence, not theater)

| Slot | Philosophy | Present requires |
|---|---|---|
| Judge A | evidence-primary | strong located evidence + majority of depth components present, none absent |
| B | coverage-primary | strong evidence + **every** component present |

Borderline criteria genuinely diverge; divergences flow through the same
evidence-ruled reconciliation, and two-step splits with resolving anchors
are preserved as dissents for human review.

## Accuracy, measured

The screener verdicts are benchmarked against hand-labeled ground truth in
the gold corpus (`GOLD_VERDICTS`, 18 graded instances: exact-match for
judge A, bounded-strictness for B) — **100% at v1.2**, enforced at ≥95% in
CI with the other nine components (`python3 scripts/nlp_benchmark.py`).

## When to use which mode

- **Autonomous**: instant triage of a draft SDD, CI-style checks, working
  without AI access, free unlimited runs. Same report pipeline, honest
  caveats.
- **AI panel** (Claude + Gemini via a runner): the judgment-grade
  evaluation for client deliverables.

Switching is a per-run dropdown; nothing else changes.
