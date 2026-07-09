# SA-graded best-SDD calibration benchmarks

A Solution Architect supplied four SDDs graded best-in-class. They are used two ways, both honest about what an SA endorsement of a *document* can and cannot establish about a *criterion*.

## 1. Present-side exemplars (accuracy validation set)

20 verbatim passages drawn from the four SDDs are mapped to ZMS criteria as **Present** cases, under `label_source = sa_exemplar` in `data/accuracy-validation-set.json`. They lifted criterion coverage from 7 to 26 of 99 (concentrated in Dim 3 Solution Fit = 13 and Dim 4 Design Specificity = 7, because build/design SDDs exercise those dimensions most).

What `sa_exemplar` means and does NOT mean:
- The SA endorsed the **document** as best-in-class. The criterion-level Present mapping was **inferred** by matching the verbatim passage to the ZMS `depth_indicator` — it is not an SA per-criterion verdict.
- Therefore `sa_exemplar` counts toward **measured self-consistency, per-class recall, and coverage**, but **NOT** toward `min_human_validated_fraction_for_full_authority`. The self-consistency check still cannot BLOCK on inferred labels; blocking continues to require real SA per-criterion labels (`human_validated` / `expert_panel`). This is enforced in `accuracy_gate.py` (human-like fraction = human_validated + expert_panel only).
- They harden the Present/Partial boundary on real SDD prose — the half the eval was weakest on — by giving the model genuine positive examples of what "good" reads like, drawn from designs an SA actually blessed.

## 2. Document-level regression anchors

`data/sa-calibration-benchmarks.json` records each SDD as a regression anchor with an expected band floor (GOOD for the three build-complete SDDs; ADEQUATE for the NWCM design-phase blueprint). A best-graded SDD that the eval scores below its floor is a **miscalibration alarm in the eval**, not a defect in the SDD. These do not feed scoring; they are an out-of-band sanity check.

## Honest limits
- No further SA review is available, so these cannot be promoted to `human_validated`. The gate stays advisory until real per-criterion SA labels exist.
- Coverage is Present-side only and concentrated in Dim 3/4. Dim 1/2 (BRD comprehension/coverage) are thin because the source BRDs were not supplied with the SDDs, and Partial/Absent boundaries are not exercised by exemplars.
- ZMS stays frozen — nothing here changes a criterion. "Good" is transparently "good per this SA's exemplars," carried as provenance on every case.
