# Mode B — SDD Review Bundle Schema (single-SDD qualitative review)

This is the bundle the Section D **review** sub-batches produce in Mode B
(sdd_review). It is consumed by `report_build_sdd_review.py`. It is
**qualitative**: there are no scores, bands, variance flags, or R1-R25 numeric
validations. The seven dimensions and ZMS criteria are a LENS for structuring
findings, not a scorecard.

The evaluator reads the SDD against the ZMS criteria (what good looks like),
the content-mapping (are the 8 components present?), and the lane's
release-crosswalk findings, then writes the judgment, the per-dimension
findings, and the prioritised recommendation backlog.

## Bundle shape

```json
{
  "run_id": "W2-2026-06-16-xxxxxxxx",
  "generated_at": "2026-06-16 15:00:00 UTC",
  "zms_version": "4.6",
  "origin_label": "off_the_shelf",
  "scoring_enabled": false,

  "verdict": "needs_targeted_refinement",
  "judgment_statement": "One-to-three sentence SA judgment in prose. State whether the design is good enough to build from, and the headline reason.",
  "rationale": "A short prose paragraph expanding the judgment: what is solid, what the blocking concerns are, how close to build-ready.",

  "findings_by_dimension": {
    "2": {"strengths": ["..."], "gaps": ["..."]},
    "3": {"strengths": ["..."], "gaps": ["...", "..."]},
    "5": {"gaps": ["..."]}
  },

  "recommendations": [
    {
      "title": "Short imperative title",
      "priority": "High",
      "what": "What to refine, concretely.",
      "why": "Why it matters from a solution-design standpoint.",
      "good": "What good looks like (sourced from the ZMS depth_indicator for the relevant criterion).",
      "lens_ref": "Dim 3 / 3C easy design"
    }
  ]
}
```

## Field rules

- `verdict` is one of: `build_ready`, `build_ready_with_conditions`,
  `needs_targeted_refinement`, `not_ready`. **Issue `build_ready` when the
  design is genuinely sound** with only minor refinements — Mode B is not
  obligated to find fault.
- `origin_label` is `zenagent` / `off_the_shelf` / `unspecified`. It is a
  **label only** and must not influence any finding, recommendation, or the
  verdict. (Bias guard — same principle as Mode A blinding.)
- `findings_by_dimension` keys are dimension numbers "1".."7" as strings; each
  block has optional `strengths` and `gaps` string arrays. Omit dimensions with
  nothing notable. This is the dimensions-as-lens structure; do NOT include
  Present/Partial/Absent verdicts or scores.
- `recommendations` is the full set; the report shows the **top-N** by
  `priority` (High > Medium > Low, stable within a priority) and routes the rest
  to an appendix. Each recommendation's `good` field should paraphrase the ZMS
  depth_indicator for the cited lens so the recommendation is concrete, not
  generic. Optional `where` (location in the SDD) and `done_when` (acceptance criterion) fields render in the comprehensive card when present. `lens_ref` (or `zms_ref`) names the dimension / criterion the
  recommendation traces to.
- Release-currency recommendations are derived from the lane's
  `release-awareness-{A}.json` (the live crosswalk), not authored here; the
  report's Appendix A renders the crosswalk findings directly.
- `scoring_enabled` reflects the `--enable-single-scoring` opt-in; when false
  (default) no numeric scoring was performed.

## What the report does with it

`report_build_sdd_review.py` renders a COMPREHENSIVE SA review: Section 1 the
judgment (BLUF verdict + release headline) with an at-a-glance synthesis (dimensions
reviewed / strengths / gaps / recommendations); Section 2 a seven-lens overview table
followed by strengths/gaps by dimension; Section 3 the top-N recommendations
(what / why / what-good-looks-like / where / done-when); then an appendix with the
calibration-coverage table and the
release-currency audit, recommendation overflow, and the review-basis
provenance note (origin-is-label-only, ZMS version, scoring state, live-vs-
register confidence, the recommend-don't-redesign boundary).
