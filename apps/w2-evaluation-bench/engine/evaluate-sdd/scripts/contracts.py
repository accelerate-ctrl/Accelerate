"""contracts.py — SINGLE SOURCE OF TRUTH for every verbatim string the
R1-R25 validator enforces character-for-character.

Why this file exists: in v3.7.2 these strings were restated independently in
score_sheet_populate.py, section-d-core.md, section-d-bundle-schema.md, and
pipeline-procedures.md — and three of the four copies drifted, so every
faithfully-authored bundle failed R7/R12/R16. Any rule that must match
verbatim now lives HERE, the validator imports it, and the regression suite
asserts the reference documents quote it exactly (test_contracts_doc_sync).

Editing rules:
- Changing any string here is a CONTRACT CHANGE: bump the evaluate-sdd minor
  version, update the three reference docs, and re-run the regression suite.
- Never edit the copies in the docs without editing here first.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------
# Framework release label — SINGLE SOURCE OF TRUTH (v4.6).
# Every component that prints a release version (SKILL.md, system prompt,
# rubric, OH, report covers, template version cells, ZMS-consumer references)
# states this string. There is no separate embedded `schema_version`: the
# whole system is one consistent v4.6 set.
# --------------------------------------------------------------------------
FRAMEWORK_VERSION = "4.6"

# --------------------------------------------------------------------------
# R15 — blinding attestation (verbatim)
# --------------------------------------------------------------------------
BLINDING_ATTESTATION = (
    "I confirm that this scoring bundle was produced without knowledge of "
    "which lane (ZennAgent or off-the-shelf) this SDD represents. All "
    "references use the blinding label assigned at intake."
)

# --------------------------------------------------------------------------
# R16 — non-bias attestation (verbatim)
# --------------------------------------------------------------------------
NON_BIAS_ATTESTATION = (
    "I confirm that every band assignment traces to a ZMS criterion verdict "
    "cited in zms_calibration_citations; on Dim 1/2/6 every band assignment "
    "also traces to an operator-BRD passage cited in per_dim_key_reasoning; "
    "no scoring was based on prior beliefs about Salesforce architecture "
    "independent of the ZMS calibration reference."
)

# --------------------------------------------------------------------------
# R7 — per_dim_truth_source strings (verbatim, keyed by dimension)
# --------------------------------------------------------------------------
EXPECTED_TRUTH_SOURCE = {
    "1": "Operator BRD (requirements truth) + ZMS calibration reference",
    "2": "Operator BRD (requirements truth) + ZMS calibration reference",
    "3": "Operator BRD (requirements truth) + Salesforce platform standards (technical truth) + ZMS calibration reference",
    "4": "Operator BRD (requirements truth) + Content Mapping (structural truth) + ZMS calibration reference",
    "5": "Operator BRD (requirements truth) + ZMS calibration reference",
    "6": "Operator BRD (requirements truth) + ZMS calibration reference",
    "7": "Operator BRD (requirements truth) + ZMS calibration reference",
}

# --------------------------------------------------------------------------
# R14 — blinding-leak scan (covers both ZenAgent spellings, ZA, OTS)
# --------------------------------------------------------------------------
BLINDING_FORBIDDEN_PATTERN = r"\b(?:Zenn?Agent|ZA|off[- ]the[- ]shelf|OTS)\b"
BLINDING_FORBIDDEN_TOKENS = re.compile(BLINDING_FORBIDDEN_PATTERN, re.IGNORECASE)


def blinding_scanner(extra_terms=None):
    """Compile the blinding-leak scanner for R14: the base lane-identity tokens
    PLUS any operator-supplied brand/product/vendor names for THIS engagement.

    The base tokens cover the ZenAgent side and the generic 'off-the-shelf'
    label. The extra terms let the operator add the actual product/tool/brand
    names of the two SDDs' sources (e.g. a vendor tool name, a competitor brand,
    a document logo/footer string), so the scan also catches identity leaking
    through branding, logos, headers/footers, or named tools — not just the
    canonical lane labels. extra_terms is a list of strings; each is matched
    case-insensitively as a whole word/phrase."""
    pat = BLINDING_FORBIDDEN_PATTERN
    if extra_terms:
        safe = [re.escape(t.strip()) for t in extra_terms if t and str(t).strip()]
        if safe:
            pat = pat + "|" + "|".join(r"\b" + s + r"\b" for s in safe)
    return re.compile(pat, re.IGNORECASE)

# --------------------------------------------------------------------------
# R12 — recognised ZMS source labels
# ("Zennify + Well-Architected" is reserved/empty at ZMS v4.6 but remains
#  recognised for forward compatibility with future register versions.)
# --------------------------------------------------------------------------
RECOGNISED_SOURCE_LABELS = {
    "Zennify SDD standard",
    "Well-Architected",
    "Zennify + Well-Architected",
}

# --------------------------------------------------------------------------
# R12 / R19 / R20 — verdict vocabulary
# --------------------------------------------------------------------------
VALID_VERDICTS = {"Present", "Partial", "Absent", "NA"}

# --------------------------------------------------------------------------
# RR cumulative cap (rubric section 7.2) — the live, load-bearing RR limit.
# --------------------------------------------------------------------------
RR_CUMULATIVE_CAP = -9

# LEGACY tier scale (Critical/Major/Minor -> -5/-3/-1). This is NOT the current
# RR deduction schedule: under the confidence-based binary model the RR value is
# single-sourced in RELEASE_SEVERITY_DEDUCTION below (-3 confirmed-not-in-force /
# -1 unverified-when-live / 0 in_force; never -5). This map is retained only as
# the back-compat mirror of release_awareness_check.SEVERITY_DEDUCTION; it is not
# consumed by any live scoring path, and R10 rejects an RR deduction of -5
# (-5 is TRUST-only).
RR_SEVERITY_DEDUCTION = {"Critical": -5, "Major": -3, "Minor": -1}

# --------------------------------------------------------------------------
# Release-currency status taxonomy. Single-sourced here; mirrored by
# release_crosswalk.py and asserted by the regression suite so the engine, the
# report, and the docs cannot drift.
#
# SCORING MODEL (v4.2 — confidence-based binary):
# The deduction is tied to EVIDENCE STRENGTH about currency, not to the
# retirement *category* (which requires dated, drift-prone knowledge). The
# descriptive status names below are retained as useful report detail (they say
# WHAT Salesforce reported), but they no longer drive different deductions:
#   - in_force                -> 0   (Salesforce affirmatively confirms current)
#   - retired/end_of_support/superseded ("confirmed not in force")
#                             -> RR_NOT_IN_FORCE_DEDUCTION (a single, unified
#                                penalty; no more -5/-3 category gradation)
#   - in_force_unverified     -> RR_UNVERIFIED_DEDUCTION, BUT ONLY when the live
#                                path actually ran this lane. If the run had no
#                                web access (live_path_used = False) every
#                                mechanism is unverified for a TOOLING reason,
#                                not a design flaw, so unverified deducts 0.
# The cumulative cap (RR_CUMULATIVE_CAP, -9/lane) is unchanged.
# --------------------------------------------------------------------------
RELEASE_STATUS = (
    "retired",              # Salesforce confirms gone — "not in force"
    "end_of_support",       # Salesforce confirms unsupported — "not in force"
    "superseded",           # Salesforce confirms a newer standard — "not in force"
    "in_force",             # current, supported, appropriate
    "in_force_unverified",  # could not confirm against a Salesforce source
)

# The three statuses that mean "Salesforce confirmed this is NOT current".
# Single-sourced so the resolver, report, and tests agree on the binary split.
RELEASE_NOT_IN_FORCE_STATUSES = ("retired", "end_of_support", "superseded")

# Deduction values (confidence-based binary model).
RR_NOT_IN_FORCE_DEDUCTION = -3   # any Salesforce-confirmed not-in-force mechanism
RR_UNVERIFIED_DEDUCTION = -1     # named, live path ran, currency NOT confirmed

# status -> RR severity label (kept for report detail; None where no deduction).
# All not-in-force statuses now share one severity tier ("Major") since the
# deduction no longer distinguishes retirement category.
RELEASE_STATUS_SEVERITY = {
    "retired": "Major",
    "end_of_support": "Major",
    "superseded": "Major",
    "in_force": None,
    "in_force_unverified": None,
}

# status -> RR deduction. unverified is handled specially by the resolver (gated
# on live_path_used); the value here is its deduction WHEN the live path ran.
# Spelled out so the regression suite can assert it.
RELEASE_SEVERITY_DEDUCTION = {
    "retired": RR_NOT_IN_FORCE_DEDUCTION,
    "end_of_support": RR_NOT_IN_FORCE_DEDUCTION,
    "superseded": RR_NOT_IN_FORCE_DEDUCTION,
    "in_force": 0,
    "in_force_unverified": RR_UNVERIFIED_DEDUCTION,
}

# Confidence labels for transparent degradation (live vs register vs neither).
RELEASE_CONFIDENCE = ("live_confirmed", "register_based", "unverified")

# The exact phrase emitted when no Salesforce-controlled source names a
# successor (Tier-3: never invent a replacement).
SUCCESSOR_UNSOURCED = "SA to confirm current successor"

# ==========================================================================
# NUMERIC PARAMETERS — SINGLE SOURCE OF TRUTH (added v4.1)
#
# Before v4.1 the band scale, the gate thresholds, the dimension maxima, and
# the coverage->score curve were restated independently in
# score_sheet_populate.py, lift_calculate.py, lane_reveal_apply.py, the report
# builders, and the harnesses, and drifted out of sync. They now live HERE.
# v4.2 adopts the four-band quality model: the band carries the disposition and
# is read on the overall total and per dimension; the gate aligns 1:1 with it.
#
# All band/gate/maxima/curve numbers now live HERE. The rubric is the canonical
# authority (it "governs scoring in case of conflict"), so these values mirror
# rubric section 3 (bands), section 8 (gate), section 2 (maxima), and section 5
# (curve). test_contracts_doc_sync asserts the rubric quotes them.
# ==========================================================================

# --- Quality band scale (rubric section 3) -------------------------------
# Four-band model: the band carries the disposition (Accept / Accept with
# changes / Rework / Redo) and is read on the overall total and per dimension.
# Same vocabulary the model emits and R6 validates, so the code-computed band
# and the model-emitted band cannot disagree. (min_pct_inclusive, label), high first.
BAND_SCALE = (
    (80.0, "STRONG"),
    (70.0, "GOOD"),
    (65.0, "ADEQUATE"),
    (0.0,  "WEAK"),
)
BAND_LABELS = ("STRONG", "GOOD", "ADEQUATE", "WEAK")

# The four-band model is band-driven: each band carries its disposition, read at
# two levels (overall total of 100 and each dimension as a percentage of its max).
BAND_MEANING = {
    "STRONG":   "Build-ready; this is the target standard.",
    "GOOD":     "Acceptable; address the noted changes first.",
    "ADEQUATE": "Failed; needs reworking before it proceeds.",
    "WEAK":     "Should be redone.",
}
BAND_DISPOSITION = {
    "STRONG":   ("Accept",              "Build-ready; this is the target standard."),
    "GOOD":     ("Accept with changes", "Acceptable; address the noted changes first."),
    "ADEQUATE": ("Rework",              "Failed; needs reworking before it proceeds."),
    "WEAK":     ("Redo",                "Should be redone."),
}

# --- Qualification gate (rubric section 8) -------------------------------
# In the four-band model the band IS the verdict. The PASS/MARGINAL_*/FAIL
# vocabulary is retained for internal consumers and maps 1:1 to the bands.
GATE_PASS_FRACTION = 0.80       # >= 80% -> STRONG / Accept (build-ready)
GATE_GOOD_FRACTION = 0.70       # 70-79% -> GOOD / Accept with changes
GATE_MARGINAL_FRACTION = 0.65   # 65-69% -> ADEQUATE / Rework;  < 65% -> WEAK / Redo
GATE_LEVELS = ("PASS", "MARGINAL_PASS", "MARGINAL_FAIL", "FAIL")
GATE_TO_BAND = {"PASS": "STRONG", "MARGINAL_PASS": "GOOD",
                "MARGINAL_FAIL": "ADEQUATE", "FAIL": "WEAK"}

# Gate verdict -> (disposition, meaning), aligned 1:1 with the four bands.
GATE_DISPOSITION = {
    "PASS":          ("Accept",              "Build-ready; this is the target standard."),
    "MARGINAL_PASS": ("Accept with changes", "Acceptable; address the noted changes first."),
    "MARGINAL_FAIL": ("Rework",              "Failed; needs reworking before it proceeds."),
    "FAIL":          ("Redo",                "Should be redone."),
}

# --- Dimension maxima (rubric section 2) ---------------------------------
# (base, integration_heavy). Dims 5 and 7 swap weights when integration-heavy.
DIM_MAX = {1: (15, 15), 2: (15, 15), 3: (20, 20), 4: (15, 15),
           5: (10, 15), 6: (10, 10), 7: (15, 10)}

# --- Dimension 4 component-presence floor cap (rubric section 6.4.1) ------
# SINGLE SOURCE OF TRUTH for the floor schedule. Read by content_mapping_
# classify.py (classifier), score_sheet_populate.py (sheet), the report
# builder, and the rubric-anchored regression test, so the classifier, the
# score sheet, the report, and the test all read ONE schedule.
#
# Schedule over the count of stub+missing components among the 8 required:
#   0        -> no cap (full Dimension-4 max of 15)
#   1 or 2   -> cap 10
#   3 or more-> cap 7
# NOTE: a count of EXACTLY 2 caps at 10, not 7. The prior engine defect
# that capped a count of 2 at 7 was fixed in v4.2; the engine
# and the rubric are identical at every count. `None` means "no cap".
DIM4_FLOOR_NO_CAP = None        # count 0 -> score by sub-criteria only (max 15)
DIM4_FLOOR_CAP_LOW = 10         # count 1 or 2
DIM4_FLOOR_CAP_HIGH = 7         # count 3+

# --- Coverage -> within-band score curve (rubric section 5 / section-d-core) ---
# Piecewise-linear, monotonic, continuous at the knots. Each tuple:
# (coverage_floor, frac_at_floor, frac_at_next_floor) applied over
# [coverage_floor, next higher floor). Highest floor first.
COVERAGE_CURVE_KNOTS = (
    (0.85, 0.90, 1.00),
    (0.70, 0.80, 0.90),
    (0.50, 0.68, 0.80),
    (0.30, 0.50, 0.68),
    (0.00, 0.00, 0.50),
)
# A wholly-absent critical component caps the result below an accepting band
# (below GOOD/70%), matching the standard: a missing build-blocker cannot Accept.
CRITICAL_ABSENT_CAP = 0.699


# --- Derivation helpers (so every consumer computes identically) ---------
def band_for_pct(pct):
    """Canonical four-band quality band (rubric section 3). Returns '' for None."""
    if pct is None:
        return ""
    for floor, label in BAND_SCALE:
        if pct >= floor:
            return label
    return BAND_LABELS[-1]


def gate_for_pct(pct, variance_flag=False):
    """Four-band qualification gate, score-driven (rubric section 8):

    >= 80%   -> PASS           (STRONG / Accept, build-ready)
    70-79%   -> MARGINAL_PASS  (GOOD / Accept with changes)
    65-69%   -> MARGINAL_FAIL  (ADEQUATE / Rework)
    < 65%    -> FAIL           (WEAK / Redo)

    variance_flag is retained for signature compatibility and surfaced as a
    soft "confirm this dimension" annotation by consumers; it does not move the
    band, which is purely score-driven in the four-band model.
    """
    if pct is None:
        return ""
    if pct >= GATE_PASS_FRACTION * 100.0:
        return "PASS"
    if pct >= GATE_GOOD_FRACTION * 100.0:
        return "MARGINAL_PASS"
    if pct >= GATE_MARGINAL_FRACTION * 100.0:
        return "MARGINAL_FAIL"
    return "FAIL"


def dim_max(dim, integration_heavy=False):
    base, ih = DIM_MAX[int(dim)]
    return ih if integration_heavy else base


def dim_4_floor_cap(stub_missing_count):
    """Canonical Dimension-4 component-presence floor cap (rubric section 6.4.1).

    Returns the cap to apply to (4A + 4B), or None for "no cap":
        0        -> None  (no cap; full max 15)
        1 or 2   -> 10
        3+       -> 7

    Single-sourced so the classifier, score sheet, report, and regression test
    cannot diverge. A count of exactly 2 caps at 10 (the count==2 -> 7 defect is
    fixed in v4.2)."""
    n = int(stub_missing_count or 0)
    if n <= 0:
        return DIM4_FLOOR_NO_CAP
    if n <= 2:
        return DIM4_FLOOR_CAP_LOW
    return DIM4_FLOOR_CAP_HIGH


def gate_threshold(dim, integration_heavy=False):
    """The 80% per-dimension gate threshold in absolute points (rubric section 8)."""
    return round(GATE_PASS_FRACTION * dim_max(dim, integration_heavy), 2)


def overall_gate_from_dims(dim_gates):
    """Roll per-dimension gate verdicts into the overall gate (rubric section 8):
    FAIL if any dim FAILs; else MARGINAL_* if any dim is marginal; else PASS."""
    vals = [g for g in dim_gates if g]
    if not vals:
        return ""
    if any(g == "FAIL" for g in vals):
        return "FAIL"
    if any(g == "MARGINAL_FAIL" for g in vals):
        return "MARGINAL_FAIL"
    if any(g == "MARGINAL_PASS" for g in vals):
        return "MARGINAL_PASS"
    return "PASS"
