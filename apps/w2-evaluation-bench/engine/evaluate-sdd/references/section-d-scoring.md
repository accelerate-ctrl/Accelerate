# Section D scoring reference (ROUTER)

This file was split in v3.7.2 to cut per-sub-batch context load. Read ONLY what the current sub-batch needs:

| When | Read |
|---|---|
| Every scoring sub-batch (4a-4d) | `section-d-core.md` (procedure, coding scheme, five-run, attestation) |
| Sub-batches 4a and 4c (Dims 1-3) | `section-d-dims-1-3.md` (anchors, category sets, Dim-3 deductions) |
| Sub-batches 4b and 4d (Dims 4-7) | `section-d-dims-4-7.md` (anchors, category sets, Dim-4 floor, weight swap) |
| Bundle assembly (end of 4b / 4d) | `section-d-bundle-schema.md` (full output schema, R1-R25 detail) |

Do not read all four into one sub-batch; the split exists to keep each scoring turn inside the context budget.

## Dimension maxima rationale (why the weights are what they are)

The dimension maxima are 15 / 15 / 20 / 15 / 10 / 10 / 15 (= 100), defined in
`contracts.DIM_MAX` (rubric section 2). They are deliberately NOT proportional to
each dimension's criterion count. The 99 ZMS criteria are distributed
11 / 9 / 36 / 20 / 10 / 7 / 6 across Dims 1-7, so Dimension 3 (Salesforce Solution
Fit) holds 36% of the criteria but is capped at 20% of the score.

This is intentional normalisation, not an oversight:
- **Capping Dim 3 at 20 points prevents its large criterion count from
  dominating the total.** Without the cap, "Salesforce solution fit" detail would
  swamp business-requirements comprehension, scope discipline, and the rest. The
  cap keeps the seven dimensions commensurable as *areas of quality*, regardless
  of how finely each is sub-divided into criteria.
- **Consequence — per-criterion leverage varies by design.** A single Dim-3
  criterion moves the score ~0.56 pt; a single Dim-7 criterion moves it ~2.50 pt
  (a ~4.5x spread). A Dim-3 miss is therefore easily averaged away within the
  20-point envelope.
- **Mitigation for the highest-stakes Dim-3 items: the critical-floor.** Of the
  seven `critical_floor_ids` (ZMS register), two are in Dim 3 — `3B.record` and
  `3B.external_user_exposure`. A miss on either CAPS the dimension regardless of
  the other 34 Dim-3 criteria, so the costliest Dim-3 errors bypass averaging.
- Dims 5 and 7 swap maxima under `integration_heavy` (see `dim_max`).

If the rubric is ever re-versioned, this rationale should be revisited alongside
the maxima; the maxima are the canonical numbers and live only in `contracts.py`.

