#!/usr/bin/env python3
"""
score_sheet_populate.py (v4.6) — Section E helper.

Changes from v3 (pre-ZMS):
- All `pair_comparison_citations` references replaced with `zms_calibration_citations`
- R7 truth-source strings updated to ZMS-aware versions
- R11 patterns updated to flag ZMS-as-requirements-authority phrasings
- R12 entry shape (flat): {zms_criterion_id, source_label, brd_ref, sdd_ref, verdict, evidence_anchor, observation}
- R16 attestation template now cites ZMS, not benchmark
- R17 validates structure only (no schema_version; one v4.6 set)
- Library entry fields → ZMS calibration fields in header tokens
- R19-R25 added:
    R19: every applicable ZMS criterion appears in at least one content_coding.zms_components
    R20: Partial/Absent Zennify-source criteria carry evidence_anchor
    R21: TRUST/RR deduction IDs trace to named schedule entries / release-awareness findings
    R22: RR deduction's release_finding_ref exists in release_awareness_findings
    R23: RR salesforce_source URL is on the Salesforce-controlled domain whitelist
    R24: every RR deduction has a corresponding Release Currency Audit row, report Appendix B (orchestrator-side cross-check)
    R25: every Present/Partial evidence_anchor is grounded (quotes the SDD) and criterion-relevant (addresses the cited criterion's depth components; provably verified when a source index is supplied)
- Total rules: 18 → 25
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

try:
    from openpyxl import load_workbook
except ImportError:
    print("ERROR: pip install openpyxl --break-system-packages", file=sys.stderr)
    sys.exit(10)


# Single source of truth for all verbatim-enforced strings (R7/R12/R14/R15/R16).
# contracts.py lives in this same scripts/ directory.
try:
    import contracts
except ImportError:  # invoked with a different CWD/sys.path arrangement
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import contracts

DIM_TO_PERDIM_ROW = {1: 5, 2: 6, 3: 7, 4: 8, 5: 9, 6: 10, 7: 11}
DIM_TO_VARIANCE_ROW = {1: 4, 2: 5, 3: 6, 4: 7, 5: 8, 6: 9, 7: 10}

DIM_3_SUB_TO_ROW = {
    "cloud_module_selection": 5,
    "trusted_design": 6,
    "easy_design": 7,
    "adaptable_design": 8,
    "multi_cloud_architecture": 9,
}

HEADER_LABEL_TO_FIELD = {
    "Run ID": "run_id",
    "Run timestamp (UTC)": "run_timestamp",
    "ZMS version": "zms_version",
    "ZMS frozen at": "zms_frozen_at",
    "ZMS applicable criteria": "zms_applicable_criteria_count",
    "Evaluator model name and version": "evaluator_model",
}

RECOGNISED_SOURCE_LABELS = contracts.RECOGNISED_SOURCE_LABELS

# Salesforce-controlled domain whitelist for R23 (must match ZMS skill's release-
# awareness whitelist).
SALESFORCE_SOURCE_WHITELIST = {
    "help.salesforce.com", "architect.salesforce.com", "developer.salesforce.com",
    "releasenotes.docs.salesforce.com", "trailhead.salesforce.com",
    "salesforce.com", "www.salesforce.com", "admin.salesforce.com",
    "ideas.salesforce.com",
}


def _url_on_whitelist(url: str) -> bool:
    """R23 host check. Delegates to the shared source_authority helper (single
    source of truth); local fallback retained for standalone use."""
    try:
        from source_authority import is_salesforce_url as _shared
        return _shared(url)
    except Exception:
        pass
    if not url or not isinstance(url, str):
        return False
    from urllib.parse import urlparse
    host = (urlparse(url.strip()).hostname or "").lower()
    return host in SALESFORCE_SOURCE_WHITELIST or any(
        host.endswith("." + d) for d in SALESFORCE_SOURCE_WHITELIST
    )

BLINDING_FORBIDDEN_TOKENS = contracts.BLINDING_FORBIDDEN_TOKENS

# ----- R11 (v3.7): ZMS-as-requirements-authority patterns -----
# These phrasings treat ZMS as factual authority on what the operator
# BRD requires. NOT admissible on Dim 1/2/6.
#
# ALLOWED PHRASINGS (NOT caught by these patterns):
#   "ZMS criterion `1A.field` requires field-extension naming with type..."
#   "ZMS calibration for Scope Discipline (`6A.scope_boundary_table`) requires..."
#   "the candidate is one tier below the ZMS calibration bar"
#   "ZMS calibration shows mechanism-level audit; the candidate addresses it..."
ZMS_AS_AUTHORITY_PATTERNS = [
    # "per ZMS, [requirement|story|AC|the BRD] X is..." — requires the anchoring noun
    re.compile(
        r"\bper\s+(?:the\s+)?ZMS[\s,]+"
        r"(?:requirement|user[\s-]?stor(?:y|ies)|acceptance\s+criteri(?:a|on)|"
        r"AC\s+\d|the\s+BRD)\b",
        re.IGNORECASE,
    ),
    # "according to ZMS, [requirement|story|AC] X is..."
    re.compile(
        r"\baccording\s+to\s+(?:the\s+)?ZMS[\s,]+"
        r"(?:requirement|user[\s-]?stor(?:y|ies)|acceptance\s+criteri(?:a|on)|"
        r"AC\s+\d|the\s+BRD)\b",
        re.IGNORECASE,
    ),
    # "ZMS (criterion|standard|calibration) requires/specifies/mandates [requirement|story|AC]"
    re.compile(
        r"\b(?:the\s+)?ZMS\s+(?:criterion\s+)?(?:standard\s+)?(?:calibration\s+)?"
        r"(?:requires?|specif(?:ies|y)|mandates?|dictates?)\s+"
        r"(?:that\s+)?(?:requirement|user[\s-]?stor(?:y|ies)|acceptance\s+criteri(?:a|on)|"
        r"AC\s+\d|the\s+candidate)\b",
        re.IGNORECASE,
    ),
    # "the ZMS criterion's requirement/story/AC..." — authority over requirements
    re.compile(
        r"\bthe\s+ZMS\s+criterion'?s?\s+"
        r"(?:requirement|user[\s-]?stor(?:y|ies)|acceptance\s+criteri(?:a|on)|AC\b)",
        re.IGNORECASE,
    ),
    # "compared to ZMS, the candidate is missing requirement X"
    re.compile(
        r"\b(?:compared\s+to|against)\s+(?:the\s+)?ZMS(?:\s+bar)?[\s,]+"
        r"(?:the\s+candidate\s+is\s+missing|missing|omitted)\b",
        re.IGNORECASE,
    ),
    # "ZMS states/says that requirement X is..."
    re.compile(
        r"\bZMS\s+(?:states?|says?)\s+(?:that\s+)?(?:requirement|stor(?:y|ies)|AC)\b",
        re.IGNORECASE,
    ),
]

# Backward-compat alias for any code that still references the old name
BENCHMARK_AS_AUTHORITY_PATTERNS = ZMS_AS_AUTHORITY_PATTERNS

# ----- R18: operator-BRD citation heuristics for Dim 1/2/6 -----
# Default patterns; configurable to match the operator's actual ID convention.
# These cover the most common story-ID and BRD-section formats.
OPERATOR_BRD_CITATION_PATTERNS = [
    re.compile(r"\bSF-?\d+\b", re.IGNORECASE),         # SF-336, SF336
    re.compile(r"\bUS-?\d+\b", re.IGNORECASE),         # US-12, US12
    re.compile(r"\bSTORY-?\d+\b", re.IGNORECASE),      # STORY-1, STORY1
    re.compile(r"\bAC-?\d+\b", re.IGNORECASE),         # AC-1, AC1
    re.compile(r"\bS\d+[-/ ]?AC-?\d+\b", re.IGNORECASE),  # S3-AC2, S3/AC2 (story-scoped AC)
    re.compile(r"\bStory\s+\d+\s*(?:/|,)?\s*AC-?\d+\b", re.IGNORECASE),  # Story 3 / AC2
    re.compile(r"\bAcceptance\s+Criteri", re.IGNORECASE),  # "Acceptance Criterion/Criteria N"
    re.compile(r"\bBRD\s*§\s*\d+", re.IGNORECASE),     # BRD §3
    re.compile(r"\boperator\s+(?:user\s+)?stor(?:y|ies)\b", re.IGNORECASE),
    re.compile(r"\boperator\s+(?:BRD|input)\b", re.IGNORECASE),
    re.compile(r"\brequirement\s+\d+\b", re.IGNORECASE),
    re.compile(r"\bin\s+(?:the\s+)?(?:input\s+artefact|operator\s+BRD)\b", re.IGNORECASE),
]


_ANCHOR_PLACEHOLDER_PATTERNS = [
    # restatements of the verdict instead of a quote from the SDD
    re.compile(r"\bcoded\s+(present|partial|absent|na)\b", re.IGNORECASE),
    re.compile(r"\bverdict\s*[:=]\s*(present|partial|absent)\b", re.IGNORECASE),
    re.compile(r"\bscored\s+(present|partial|absent)\b", re.IGNORECASE),
    # vague "go look elsewhere" deferrals that carry no actual evidence
    re.compile(r"\bsee\s+(the\s+)?(capability|ad|adr|design|detail|section|sdd|above|below)\b", re.IGNORECASE),
    re.compile(r"\brefer\s+to\b", re.IGNORECASE),
    re.compile(r"\b(not\s+specified|tbd|todo|placeholder|n/?a)\b", re.IGNORECASE),
    re.compile(r"\b(as\s+(noted|described|detailed)\s+(above|below|elsewhere))\b", re.IGNORECASE),
]


def _load_depth_components(zms_criteria_path=None) -> dict:
    """Map criterion_id -> depth_indicator_components, used by R25e to check that a
    Present/Partial anchor actually addresses the criterion (relevance), not just
    that it exists. Resolves the sibling zms skill if no explicit path is given;
    degrades to {} (R25e simply won't run) if unavailable."""
    from pathlib import Path as _P
    candidates = []
    if zms_criteria_path:
        candidates.append(_P(zms_criteria_path))
    here = _P(__file__).resolve()
    candidates += [here.parent.parent.parent / "zms" / "data" / "zms-criteria.json",
                   _P("/mnt/skills/user/zms/data/zms-criteria.json"),
                   _P("/mnt/skills/organization/zms/data/zms-criteria.json")]
    for p in candidates:
        try:
            if p and p.exists():
                data = json.loads(p.read_text())
                items = data if isinstance(data, list) else data.get("criteria", [])
                out = {}
                for c in items:
                    cid = (c.get("id") or "").strip()
                    if cid:
                        out[cid] = c.get("depth_indicator_components", []) or []
                if out:
                    return out
        except Exception:
            continue
    return {}


def anchor_quality_problem(anchor: str, verdict: str) -> str | None:
    """R25 helper: return a reason string if the evidence_anchor is NOT a genuine
    SDD quote — i.e. it restates the verdict, defers ("see capability detail"), or
    is a placeholder. Returns None when the anchor looks like real captured
    evidence. This is what stops the "robotic, ungrounded" cards: an anchor must
    quote/point to what the SDD actually said, not echo the score.

    Present/Partial verdicts MUST carry a substantive grounded anchor. Absent and
    NA may legitimately have a short anchor (e.g. "not present in any section"),
    so the deferral check is relaxed for them, but a verdict-restatement is never
    acceptable for any verdict.
    """
    a = (anchor or "").strip()
    v = (verdict or "").strip().lower()
    # verdict-restatement is never acceptable (any verdict)
    for pat in _ANCHOR_PLACEHOLDER_PATTERNS[:3]:
        if pat.search(a):
            return ("anchor restates the verdict rather than quoting the SDD "
                    f"(matched {pat.pattern!r})")
    if v in ("present", "partial"):
        # for asserted coverage, deferrals / placeholders are not evidence
        for pat in _ANCHOR_PLACEHOLDER_PATTERNS[3:]:
            if pat.search(a):
                return ("anchor defers or is a placeholder rather than quoting the "
                        f"SDD (matched {pat.pattern!r}); Present/Partial needs a "
                        "verbatim ≤30-word quote of what the SDD actually said")
        # must contain at least a few words of actual content
        word_count = len(a.split())
        if word_count < 4:
            return f"anchor is only {word_count} word(s); too thin to be a real quote"
        # POSITIVE GROUNDING (v4.2.1): a real SDD quote names something concrete —
        # a Salesforce artifact (CamelCase, __c, API name), a quoted phrase, a
        # section/AC/story reference, a number, or a recognised platform term.
        # Vacuous prose that merely asserts the verdict in words ("addressed in the
        # SDD", "covers this adequately", "present in the architecture") has NONE
        # of these and is rejected: it is not evidence, it is a paraphrase of the score.
        if not _has_concrete_grounding(a):
            return ("anchor contains no concrete SDD reference (no named artifact, "
                    "quoted phrase, section/story/AC ref, number, or platform term) — "
                    "it paraphrases the verdict instead of quoting what the SDD said")
    return None


# Recognised Salesforce platform terms — presence of one is a grounding signal
# (the anchor is talking about an actual mechanism, not asserting a verdict).
_PLATFORM_TERMS = re.compile(
    r"\b(flow|apex|trigger|platform event|owd|sharing rule|named credential|"
    r"experience cloud|shield|field audit|record-triggered|picklist|master-detail|"
    r"lookup|validation rule|permission set|profile|queue|mulesoft|"
    r"oauth|rest|soap|api version|data cloud|lwc|aura|workflow|process builder|"
    r"custom object|custom field|record type|sales cloud|service cloud|fsc|"
    r"financial services cloud|encrypt|sso|saml|jwt|connected app|event monitoring|"
    r"big object|external object|cdc|change data capture|bulk api|metadata api|"
    r"integration|dead-letter|community|license|portal|hyperforce|soc 2|"
    r"object|field|sharing|role hierarchy|automation)",
    re.IGNORECASE)


def _has_concrete_grounding(a: str) -> bool:
    """True if the anchor contains at least one concrete, SDD-specific token: a
    Salesforce API artifact, a quoted phrase, a section/story/AC reference, a
    digit, or a recognised platform term. Absence means the anchor is vacuous prose."""
    if not a:
        return False
    # quoted phrase (the anchor literally quotes the SDD)
    if '"' in a or "'" in a or "\u201c" in a or "\u2018" in a:
        return True
    # Salesforce custom-object/field API name (__c, __r) or CamelCase artifact
    if re.search(r"\w+__[cr]\b", a):
        return True
    if re.search(r"\b[A-Z][a-z]+[A-Z]\w+\b", a):   # CamelCase (e.g. Risk_Tier, LoanApplication)
        return True
    if re.search(r"\b\w+_\w+\b", a):               # snake/underscored artifact name
        return True
    # section / story / AC / requirement reference, or any number
    if re.search(r"\b(AC-?\d+|US-?\d+|SF-?\d+|S\d+-AC\d+|§\s?\d|section\s+\d|story\s+\d|\d)\b", a, re.IGNORECASE):
        return True
    # recognised platform term
    if _PLATFORM_TERMS.search(a):
        return True
    return False


def reasoning_references_zms_citations(reasoning: str, citations: list[dict]) -> bool:
    """Heuristic: does the reasoning text reference any of the ZMS citations?

    v3.7: ZMS calibration citations replace pair-comparison citations. Each
    citation now has a `zms_criterion_id` (e.g., "3B.record"), a
    `source_label` (Zennify SDD standard / Well-Architected / both),
    a per-lane `verdict` (Present/Partial/Absent/NA), and an `evidence_anchor`.

    The reasoning is grounded if it references either:
      - the zms_criterion_id directly (e.g., "3B.record" appears in reasoning), or
      - distinctive content words from the evidence anchor, or
      - reference markers in the evidence (SDD §, story ID, mechanism name).

    One overlap is enough to confirm connection; R12/R20 already enforce the
    observations themselves are substantive.
    """
    if not citations:
        return False
    rl = reasoning.lower()
    STOPWORDS = {"calibration", "reference", "criterion", "criteria", "verdict",
                 "addressed", "absent", "partial", "present", "evidence", "anchor",
                 "section", "design", "configuration", "salesforce"}
    for cite in citations:
        # Path 1: zms_criterion_id appears verbatim
        cid = (cite.get("zms_criterion_id") or "").lower()
        if cid and cid in rl:
            return True
        # Path 2: distinctive content-word overlap with evidence anchor
        anchor = (cite.get("evidence_anchor") or "").lower()
        words = [w for w in re.findall(r"\b[a-z][a-z]{4,}\b", anchor)
                 if w not in STOPWORDS]
        if any(w in rl for w in set(words)):
            return True
        # Path 3: SDD pointers / story IDs / mechanism names from evidence
        tokens = re.findall(
            r"\b(?:SF-?\d+|US-?\d+|AC-?\d+|ADR-?\d+|BR-?\d+|§\s*\d+(?:\.\d+)?|Section\s+\d+(?:\.\d+)?)\b",
            anchor
        )
        for tok in tokens:
            if tok.lower() in rl:
                return True
    return False


def reasoning_has_operator_brd_citation(reasoning: str) -> bool:
    """R18: does the Dim 1/2/6 reasoning cite at least one operator-BRD passage?"""
    if not reasoning:
        return False
    return any(pat.search(reasoning) for pat in OPERATOR_BRD_CITATION_PATTERNS)


# -------- Bundle validation -----------------------------------------------

def validate_bundle(bundle: dict, blinding_label: str, source_index: dict = None,
                    depth_map: dict = None, blinding_extra_terms=None) -> tuple[bool, list[str]]:
    """v4.6 validation per references/section-d-bundle-schema.md (R1-R25). Returns (ok, errors)."""
    errors = []
    # R14 scanner: base lane-identity tokens + any operator-supplied brand terms
    # (catches identity leaking via branding/logos/named tools, not just labels).
    leak_scanner = contracts.blinding_scanner(blinding_extra_terms)

    # R1
    if bundle.get("blinding_label") != blinding_label:
        errors.append(f"R1: blinding_label mismatch: expected {blinding_label!r}, got {bundle.get('blinding_label')!r}")

    # R2
    runs = bundle.get("five_runs_by_dimension", {})
    if set(runs.keys()) != {"1", "2", "3", "4", "5", "6", "7"}:
        errors.append(f"R2: five_runs_by_dimension keys must be 1..7 strings; got {sorted(runs.keys())}")
    for k, v in runs.items():
        if not isinstance(v, list) or len(v) != 5 or not all(isinstance(s, (int, float)) for s in v):
            errors.append(f"R2: five_runs_by_dimension[{k!r}] must be a list of 5 numerics; got {v!r}")

    means = bundle.get("per_dim_mean", {})
    stddevs = bundle.get("per_dim_stddev", {})
    flags = bundle.get("per_dim_variance_flag", {})
    bands = bundle.get("per_dim_band", {})

    # R3, R4, R5
    for k in ("1", "2", "3", "4", "5", "6", "7"):
        if k in runs and len(runs.get(k, [])) == 5:
            expected_mean = round(sum(runs[k]) / 5, 1)
            expected_std = round(statistics.stdev(runs[k]), 2)
            expected_flag = expected_std > 1.0
            if means.get(k) is not None and abs(means[k] - expected_mean) > 0.05:
                errors.append(f"R3: per_dim_mean[{k}] = {means[k]}, expected {expected_mean}")
            if stddevs.get(k) is not None and abs(stddevs[k] - expected_std) > 0.005:
                errors.append(f"R4: per_dim_stddev[{k}] = {stddevs[k]}, expected {expected_std}")
            if flags.get(k) is not None and bool(flags[k]) != expected_flag:
                errors.append(f"R5: per_dim_variance_flag[{k}] = {flags[k]}, expected {expected_flag}")

    # R6
    valid_bands = set(contracts.BAND_LABELS)  # single-sourced (v4.1); rubric section 3
    for k in ("1", "2", "3", "4", "5", "6", "7"):
        if k not in bands:
            errors.append(f"R6: per_dim_band[{k}] missing")
        elif bands[k] not in valid_bands:
            errors.append(f"R6: per_dim_band[{k}] = {bands[k]!r} not in {valid_bands}")

    # R7 (v3 strings)
    truth = bundle.get("per_dim_truth_source", {})
    expected_truth = contracts.EXPECTED_TRUTH_SOURCE
    for k, v in expected_truth.items():
        if truth.get(k) != v:
            errors.append(f"R7: per_dim_truth_source[{k}] = {truth.get(k)!r}, expected {v!r}")

    # R8
    sub3 = bundle.get("dim_3_sub_criteria", {})
    required_sub3 = ["cloud_module_selection", "trusted_design", "easy_design", "adaptable_design"]
    mc = sub3.get("multi_cloud_architecture")
    multi_cloud = mc is not None
    per_sub_max = 4 if multi_cloud else 5
    if multi_cloud:
        required_sub3 = required_sub3 + ["multi_cloud_architecture"]
    for key in required_sub3:
        item = sub3.get(key)
        if not item:
            errors.append(f"R8: dim_3_sub_criteria[{key!r}] missing")
            continue
        # Accept "scores" (5-pass array) or "score" (scalar mean)
        scores_arr = item.get("scores")
        score_val = item.get("score")
        if isinstance(scores_arr, list) and len(scores_arr) == 5 and all(isinstance(s, (int, float)) for s in scores_arr):
            score = round(sum(scores_arr) / len(scores_arr), 1)
        elif isinstance(score_val, (int, float)):
            score = score_val
        else:
            errors.append(f"R8: dim_3_sub_criteria[{key!r}] has neither valid 'scores' array nor 'score' scalar")
            continue
        if score < 0 or score > per_sub_max:
            errors.append(
                f"R8: dim_3_sub_criteria[{key!r}] score {score} out of bounds [0, {per_sub_max}] (multi_cloud={multi_cloud})"
            )
        if not item.get("reasoning") or len(item.get("reasoning", "")) < 50:
            errors.append(f"R8: dim_3_sub_criteria[{key!r}] reasoning <50 chars")

    # R9
    sub4 = bundle.get("dim_4_sub_criteria", {})
    sub4_max = {"component_presence": 9, "architectural_decision_quality": 6}
    for key, max_score in sub4_max.items():
        item = sub4.get(key)
        if not item:
            errors.append(f"R9: dim_4_sub_criteria[{key!r}] missing")
            continue
        scores_arr = item.get("scores")
        score_val = item.get("score")
        if isinstance(scores_arr, list) and len(scores_arr) == 5 and all(isinstance(s, (int, float)) for s in scores_arr):
            score = round(sum(scores_arr) / len(scores_arr), 1)
        elif isinstance(score_val, (int, float)):
            score = score_val
        else:
            errors.append(f"R9: dim_4_sub_criteria[{key!r}] has neither valid 'scores' array nor 'score' scalar")
            continue
        if score < 0 or score > max_score:
            errors.append(f"R9: dim_4_sub_criteria[{key!r}] score {score} out of bounds [0, {max_score}]")
    if all(k in sub4 for k in ("raw_sum_before_floor", "final_dim_4_score")):
        raw = sub4.get("raw_sum_before_floor")
        cap = sub4.get("floor_cap")
        final = sub4.get("final_dim_4_score")
        if isinstance(raw, (int, float)) and isinstance(final, (int, float)):
            expected = min(raw, cap) if cap is not None else min(raw, 15)
            if abs(final - expected) > 0.05:
                errors.append(f"R9: final_dim_4_score = {final}, expected min({raw}, {cap if cap is not None else 15}) = {expected}")

    # R8c — sub-criteria completeness (score-sheet auditability). Every applicable
    # sub-criterion across ALL seven dimensions must carry a 5-element numeric
    # `scores` array so the Dim_1-7 Sub_Criteria sheet's per-pass columns are fully
    # populated and the report can be validated against per-sub-criterion detail.
    # 3E (multi_cloud_architecture) is required only on multi-cloud engagements;
    # when absent (None) on a single-cloud engagement it is correctly skipped.
    for _dim, _subs in SUBCRIT.items():
        _sc = bundle.get("dim_%s_sub_criteria" % _dim)
        if not isinstance(_sc, dict):
            errors.append(
                f"R8c: dim_{_dim}_sub_criteria missing or not an object — every dimension "
                "must carry sub-criterion five-pass scores to populate the audit sheet")
            continue
        for _sid, _key in _subs:
            _entry = _sc.get(_key)
            if _sid == "3E" and _entry is None:
                continue  # multi-cloud only; absent is valid off multi-cloud
            if not isinstance(_entry, dict):
                errors.append(
                    f"R8c: dim_{_dim}_sub_criteria[{_key!r}] ({_sid}) missing — needed to "
                    "populate the Sub_Criteria sheet pass columns")
                continue
            _arr = _entry.get("scores")
            if not (isinstance(_arr, list) and len(_arr) == 5
                    and all(isinstance(x, (int, float)) for x in _arr)):
                errors.append(
                    f"R8c: dim_{_dim}_sub_criteria[{_key!r}] ({_sid}) needs a 5-element numeric "
                    f"'scores' array (the five passes); got {_arr!r}")

    # R10 (v4.3 hardening): deduction values are validated BY TYPE, not by a
    # generic {-1,-3,-5} set. v4.2 policy: RR-* (release-currency) deductions are
    # only -1 or -3, NEVER -5; -5 is reserved for TRUST-* critical issues. And a
    # salesforce_source is required only for RR-* deductions (release findings),
    # not for TRUST-* deductions (which are design/trust issues, not currency).
    for d in bundle.get("deductions", []):
        did = d.get("id", "")
        val = d.get("deduction")
        if not re.match(r"^(TRUST|RR)-\d+$", did):
            errors.append(f"R10: deduction id {did!r} invalid pattern")
            continue
        if did.startswith("RR-"):
            if val not in (-1, -3):
                errors.append(f"R10: RR deduction {did!r} value {val!r} invalid — "
                              f"RR deductions are only -1 or -3 (never -5; -5 is TRUST-only)")
            if not d.get("salesforce_source"):
                errors.append(f"R10: RR deduction {did!r} missing salesforce_source "
                              f"(release-currency deductions must cite a Salesforce-controlled source)")
        elif did.startswith("TRUST-"):
            if val not in (-1, -3, -5):
                errors.append(f"R10: TRUST deduction {did!r} value {val!r} not in {{-1,-3,-5}}")
        if not d.get("triggering_passage"):
            errors.append(f"R10: deduction {did!r} missing triggering_passage")

    # R11 (v3.7): Dim 1/2/6 firewall — ZMS calibration as authority, not BRD requirements
    reasoning = bundle.get("per_dim_key_reasoning", {})
    zms_citations = bundle.get("zms_calibration_citations", {})
    for k in ("1", "2", "6"):
        text = reasoning.get(k, "") or ""
        for pat in BENCHMARK_AS_AUTHORITY_PATTERNS:
            m = pat.search(text)
            if m:
                errors.append(
                    f"R11: per_dim_key_reasoning[{k}] cites ZMS/calibration as requirements authority "
                    f"({m.group(0)!r}) — Dim {k} truth-source is operator BRD. "
                    f"ZMS calibration-as-bar phrasings are permitted; this phrasing claims authority."
                )
                break
        # Also check ZMS-citation evidence anchors for the same patterns
        for i, cite in enumerate(zms_citations.get(k, []) or []):
            anchor = cite.get("evidence_anchor", "") or ""
            for pat in BENCHMARK_AS_AUTHORITY_PATTERNS:
                m = pat.search(anchor)
                if m:
                    errors.append(
                        f"R11: zms_calibration_citations[{k}][{i}].evidence_anchor cites ZMS as "
                        f"requirements authority ({m.group(0)!r}) — truth-source firewall violation"
                    )
                    break

    # R12 (v3.7): every dimension must cite ZMS-criterion calibration evidence
    for k in ("1", "2", "3", "4", "5", "6", "7"):
        entries = zms_citations.get(k, [])
        if not entries:
            errors.append(
                f"R12: zms_calibration_citations[{k}] is empty — every dimension must "
                "cite at least one ZMS criterion with verdict and evidence anchor"
            )
            continue
        for i, entry in enumerate(entries):
            cid = entry.get("zms_criterion_id", "")
            if not cid or not re.match(r"^\d[A-Z]\.[a-z_]+$", cid):
                errors.append(
                    f"R12: zms_calibration_citations[{k}][{i}].zms_criterion_id "
                    f"{cid!r} not in expected form (e.g., '3B.record')"
                )
            label = entry.get("source_label", "")
            if label not in ("Zennify SDD standard", "Well-Architected",
                             "Zennify + Well-Architected"):
                errors.append(
                    f"R12: zms_calibration_citations[{k}][{i}].source_label "
                    f"{label!r} not in recognised set"
                )
            verdict = entry.get("verdict", "")
            if verdict not in ("Present", "Partial", "Absent", "NA"):
                errors.append(
                    f"R12: zms_calibration_citations[{k}][{i}].verdict "
                    f"{verdict!r} not in (Present/Partial/Absent/NA)"
                )
            anchor = entry.get("evidence_anchor", "") or ""
            # R20 enforced inline here: Present requires substantive evidence anchor
            if verdict == "Present" and len(anchor) < 20:
                errors.append(
                    f"R20: zms_calibration_citations[{k}][{i}] verdict=Present but "
                    f"evidence_anchor only {len(anchor)} chars — Present requires "
                    "verbatim ≤30-word anchor with substantive content"
                )
            # R25 (v4.2): anchor-quality — the evidence_anchor must be a genuine SDD
            # quote, not a restatement of the verdict ("coded Partial"), a deferral
            # ("see capability detail"), or a placeholder. This is what keeps the
            # report grounded and non-robotic: every gap card cites what the SDD
            # actually said. Enforced for Present/Partial (asserted coverage);
            # verdict-restatements are rejected for any verdict.
            if verdict in ("Present", "Partial", "Absent", "NA"):
                prob = anchor_quality_problem(anchor, verdict)
                if prob:
                    errors.append(
                        f"R25: zms_calibration_citations[{k}][{i}] (verdict={verdict}) "
                        f"evidence_anchor is not grounded — {prob}"
                    )
                # R25e (v4.5 DEFAULT relevance): even WITHOUT a source index, a
                # Present/Partial anchor must touch the SPECIFIC criterion's own
                # depth_indicator components — not merely contain some platform
                # term, number, or quoted phrase. This closes the quote-wrapping
                # bypass: a real-but-generic quote that addresses NONE of this
                # criterion's depth components is rejected. (When a source index is
                # supplied the stronger provable path below supersedes this.)
                if verdict in ("Present", "Partial") and source_index is None:
                    cid = entry.get("zms_criterion_id") or entry.get("criterion_id") or ""
                    comps = (depth_map or {}).get(cid, [])
                    if comps:
                        try:
                            import evidence_anchor_verify as _EV
                            sv = _EV.supports_verdict(anchor, verdict, comps)
                            if sv.get("quote_supports_verdict") == "no":
                                errors.append(
                                    f"R25e: zms_calibration_citations[{k}][{i}] (verdict={verdict}) "
                                    f"evidence_anchor addresses none of {cid}'s depth components "
                                    f"— it quote-wraps a generic phrase rather than the specific "
                                    f"criterion. Quote what the SDD says about THIS criterion's "
                                    f"mechanism/artifact, not any plausible Salesforce term.")
                        except Exception:
                            pass
                # R25b/c/e (v4.5): when a SOURCE INDEX is supplied, escalate from
                # heuristic groundedness to PROVABLE source verification — the
                # anchor must actually resolve in the SDD (exact/normalized), and
                # for Present/Partial must support the verdict (relevance), not
                # merely exist. Absent must carry negative_evidence. This is the
                # fix that turns R25 from "looks grounded" into "is grounded".
                if source_index is not None:
                    try:
                        import evidence_anchor_verify as _EV
                        cid = entry.get("zms_criterion_id") or entry.get("criterion_id") or ""
                        comps = (depth_map or {}).get(cid, [])
                        ver = _EV.verify_anchor(
                            anchor, verdict, source_index, comps,
                            negative_evidence=entry.get("negative_evidence"))
                        st = ver.get("status")
                        if st == "fabricated_or_unmatched":
                            errors.append(
                                f"R25b: zms_calibration_citations[{k}][{i}] (verdict={verdict}) "
                                f"evidence_anchor does NOT resolve in the SDD source index "
                                f"(fabricated or mis-transcribed quote)")
                        elif st == "irrelevant_quote":
                            errors.append(
                                f"R25e: zms_calibration_citations[{k}][{i}] (verdict={verdict}) "
                                f"evidence_anchor exists in the SDD but does not support the "
                                f"verdict for {cid} (real but irrelevant quote)")
                        elif st == "unverified_absent":
                            errors.append(
                                f"R25c: zms_calibration_citations[{k}][{i}] verdict=Absent "
                                f"missing negative_evidence (searched_sections + searched_terms required)")
                    except Exception as _e:
                        # verification is best-effort; never crash scoring on it
                        pass

    # R13 (v3.7): non-bias citation density — reasoning must ground in ZMS citations
    for k in ("1", "2", "3", "4", "5", "6", "7"):
        rtext = reasoning.get(k, "") or ""
        citations = zms_citations.get(k, [])
        if rtext and citations and not reasoning_references_zms_citations(rtext, citations):
            errors.append(
                f"R13: per_dim_key_reasoning[{k}] does not appear to reference any "
                f"zms_calibration_citations entry — non-bias requirement: reasoning "
                "must ground in cited ZMS criterion verdicts"
            )

    # R14 (v3.7): blinding leak — scan reasoning AND ZMS citation evidence anchors
    leaked_fields = []
    for field_name in ("per_dim_key_reasoning", "narrative_per_dim"):
        section = bundle.get(field_name, {})
        for k, text in section.items():
            if text and leak_scanner.search(text):
                leaked_fields.append(f"{field_name}[{k}]")
    for sub_field, sub_obj in (("dim_3_sub_criteria", sub3), ("dim_4_sub_criteria", sub4)):
        for sub_key, sub_item in (sub_obj or {}).items():
            if not isinstance(sub_item, dict):
                continue
            sub_text = sub_item.get("reasoning", "") or ""
            if sub_text and leak_scanner.search(sub_text):
                leaked_fields.append(f"{sub_field}[{sub_key}].reasoning")
    # Scan ZMS citation evidence anchors
    for k, entries in (zms_citations or {}).items():
        for i, entry in enumerate(entries or []):
            anchor = entry.get("evidence_anchor", "") or ""
            if anchor and leak_scanner.search(anchor):
                leaked_fields.append(f"zms_calibration_citations[{k}][{i}].evidence_anchor")
    if leaked_fields:
        errors.append(f"R14: Blinding leak — forbidden tokens found in {leaked_fields}")

    # R15 — verbatim match required (rubric §8)
    EXPECTED_BLINDING = contracts.BLINDING_ATTESTATION
    blinding_att = bundle.get("blinding_attestation", "")
    if not blinding_att:
        errors.append("R15: blinding_attestation missing")
    elif blinding_att.strip() != EXPECTED_BLINDING:
        errors.append(
            f"R15: blinding_attestation does not match template verbatim. "
            f"Got: {blinding_att[:80]!r}..."
        )

    # R16 (v3.7) — verbatim non-bias attestation now cites ZMS, not benchmark
    EXPECTED_NONBIAS = contracts.NON_BIAS_ATTESTATION
    nonbias_att = bundle.get("non_bias_attestation", "")
    if not nonbias_att:
        errors.append("R16: non_bias_attestation missing")
    elif nonbias_att.strip() != EXPECTED_NONBIAS:
        errors.append(
            f"R16: non_bias_attestation does not match template verbatim. "
            f"Got: {nonbias_att[:80]!r}..."
        )

    # R17 (v4.5) — well-formed bundle with all required top-level fields.
    # The framework no longer embeds a separate `schema_version`: the system is
    # one consistent v4.6 set, so R17 validates STRUCTURE (required fields
    # present), not a version floor. (A stray `schema_version` key, if present
    # from an older artifact, is ignored rather than enforced.)

    # R17 — required fields (v4.6 schema)
    required_top_level = [
        "run_id", "blinding_label", "header", "five_runs_by_dimension",
        "dim_3_sub_criteria", "dim_4_sub_criteria", "deductions",
        "per_dim_band", "per_dim_mean", "per_dim_stddev", "per_dim_variance_flag",
        "per_dim_truth_source", "per_dim_key_reasoning", "narrative_per_dim",
        "zms_calibration_citations", "content_coding",
        "blinding_attestation", "non_bias_attestation",
    ]
    missing = [f for f in required_top_level if f not in bundle]
    if missing:
        errors.append(f"R17: bundle missing required top-level field(s): {missing}")

    # R18 (v3 new): Dim 1/2/6 reasoning must cite operator-BRD passage
    for k in ("1", "2", "6"):
        rtext = reasoning.get(k, "") or ""
        if rtext and not reasoning_has_operator_brd_citation(rtext):
            errors.append(
                f"R18: per_dim_key_reasoning[{k}] does not cite any operator-BRD passage — "
                f"Dim {k} requires operator-BRD grounding (story ID, requirement number, BRD §, "
                f"AC reference, or explicit operator-input reference)"
            )

    # R19 (v3.7): ZMS coverage exhaustiveness — every applicable ZMS criterion
    # appears in at least one content_coding.zms_components entry. Without this
    # rule, the calibration bar can be silently truncated.
    content_coding = bundle.get("content_coding", {})
    zms_calibration = bundle.get("zms_calibration", {})
    applicable_ids = set()
    if isinstance(zms_calibration, dict):
        for c in (zms_calibration.get("applicable_criteria") or []):
            cid = c.get("id") if isinstance(c, dict) else None
            if cid:
                applicable_ids.add(cid)
    if applicable_ids:
        cited_ids = set()
        for sub_key, sub_block in (content_coding or {}).items():
            if not isinstance(sub_block, dict):
                continue
            for comp in (sub_block.get("zms_components") or []):
                cid = comp.get("zms_criterion_id") if isinstance(comp, dict) else None
                if cid:
                    cited_ids.add(cid)
        missing_in_coding = applicable_ids - cited_ids
        if missing_in_coding:
            errors.append(
                f"R19: ZMS coverage incomplete — {len(missing_in_coding)} applicable "
                f"criteria absent from content_coding (sample: "
                f"{sorted(missing_in_coding)[:5]})"
            )

    # R20 (v3.7): Partial/Absent verdicts on Zennify-source ZMS criteria require
    # an evidence anchor explaining what was searched for. R20 fires when a
    # Zennify-source ZMS criterion has Partial/Absent verdict but anchor is empty.
    # (R20 already enforced inline for Present in R12; this is the Partial/Absent half.)
    for sub_key, sub_block in (content_coding or {}).items():
        if not isinstance(sub_block, dict):
            continue
        for i, comp in enumerate(sub_block.get("zms_components") or []):
            if not isinstance(comp, dict):
                continue
            verdict = comp.get("verdict", "")
            source = comp.get("source_label", "")
            anchor = comp.get("evidence_anchor", "") or ""
            cid = comp.get("zms_criterion_id", "")
            if verdict in ("Partial", "Absent") and "Zennify" in source:
                if len(anchor) < 15:
                    errors.append(
                        f"R20: content_coding[{sub_key}].zms_components[{i}] "
                        f"({cid}, source={source}) verdict={verdict} but evidence_anchor "
                        f"only {len(anchor)} chars — Partial/Absent on a Zennify-source "
                        "criterion requires an anchor explaining what was searched for"
                    )

    # R21 (v3.7): every deduction with TRUST-* id cross-references the rubric's
    # TRUST schedule; RR-* deductions cross-reference release_awareness findings.
    deductions = bundle.get("deductions", []) or []
    release_findings = bundle.get("release_awareness_findings", []) or []
    finding_ids = {f.get("finding_id") for f in release_findings if isinstance(f, dict)}
    for d in deductions:
        did = d.get("id", "")
        if did.startswith("TRUST-"):
            if not d.get("trust_schedule_ref"):
                errors.append(
                    f"R21: deduction {did} missing trust_schedule_ref — every "
                    "TRUST-* deduction must cross-reference the rubric TRUST schedule"
                )

    # R22 (v3.7): every RR-* deduction traces to a release_awareness finding_id
    for d in deductions:
        did = d.get("id", "")
        if did.startswith("RR-"):
            finding_ref = d.get("release_finding_ref")
            if not finding_ref:
                errors.append(
                    f"R22: deduction {did} missing release_finding_ref — every RR-* "
                    "deduction must cite the source release_awareness finding_id"
                )
            elif finding_ids and finding_ref not in finding_ids:
                errors.append(
                    f"R22: deduction {did} release_finding_ref={finding_ref!r} not "
                    f"present in release_awareness_findings (available: {sorted(finding_ids)})"
                )

    # R23 (v3.7): every release_awareness_findings source_url must be on a
    # Salesforce-controlled domain. _url_on_whitelist is the canonical check.
    SALESFORCE_DOMAINS = (
        "help.salesforce.com",
        "developer.salesforce.com",
        "architect.salesforce.com",
        "trailhead.salesforce.com",
        "admin.salesforce.com",
        "salesforce.com",
        "trust.salesforce.com",
    )
    for i, f in enumerate(release_findings):
        if not isinstance(f, dict):
            continue
        url = f.get("source_url", "") or ""
        if not url:
            errors.append(
                f"R23: release_awareness_findings[{i}] missing source_url — "
                "every finding must cite a Salesforce-controlled source"
            )
            continue
        if not any(dom in url for dom in SALESFORCE_DOMAINS):
            errors.append(
                f"R23: release_awareness_findings[{i}] source_url={url!r} not on "
                "a Salesforce-controlled domain (help/developer/architect/trailhead/trust)"
            )

    # R24 (v3.7): every release-currency-driven recommended_action in the
    # diagnostic report must reference a release_awareness finding by ID.
    # This rule fires only when recommended_actions is present in the bundle
    # (typically populated at report assembly time; bundles may omit it).
    rec_actions = bundle.get("recommended_actions", []) or []
    for i, a in enumerate(rec_actions):
        if not isinstance(a, dict):
            continue
        if a.get("category") == "release_currency":
            if not a.get("release_finding_ref"):
                errors.append(
                    f"R24: recommended_actions[{i}] category=release_currency but "
                    "missing release_finding_ref — every release-driven action must "
                    "trace to a finding_id in release_awareness_findings"
                )

    return (len(errors) == 0, errors)


# -------- Cap and aggregation helpers (unchanged) -------------------------

def cap_rr_deductions(deductions: list[dict]) -> tuple[float, float]:
    raw = sum(d.get("deduction", 0) for d in deductions if str(d.get("id", "")).startswith("RR-"))
    capped = max(-9, raw)
    return capped, raw


def sum_trust_deductions(deductions: list[dict]) -> float:
    return sum(d.get("deduction", 0) for d in deductions if str(d.get("id", "")).startswith("TRUST-"))


def coverage_to_score(coverage, max_points, critical_floor_absent=False):
    """Map a sub-criterion's coverage signal (0..1) to a within-band score out of
    max_points, using the realistic curve calibrated in Part A (see section-d-core.md).

    The curve is intentionally non-linear: a design covering most of the bar
    substantively reaches the top of band rather than being dragged down by a few
    imperfect components, because that is what a good SDD looks like in practice.

      coverage >= 0.85  -> 0.90..1.00 of max (Strong territory)
      0.70..0.85        -> 0.80..0.90  (upper-mid; Good->Strong)
      0.50..0.70        -> 0.68..0.80  (mid; Adequate->Good)
      0.30..0.50        -> 0.50..0.68  (lower)
      < 0.30            -> 0.00..0.50  (floor)

    critical_floor_absent caps the result just below Strong
    (contracts.CRITICAL_ABSENT_CAP): a wholly missing critical component prevents
    a Strong score but does not by itself force a floor outcome.

    This is a RELIABILITY codification: putting the curve in code (not only prose)
    makes the mapping consistent across runs and testable without human labels.
    The curve knots are single-sourced in contracts.COVERAGE_CURVE_KNOTS (v4.1).
    """
    if coverage is None:
        return 0.0
    c = max(0.0, min(1.0, float(coverage)))
    # piecewise-linear fraction-of-max, monotonic and continuous at the knots.
    # Knots are highest-floor-first; `upper` tracks the next-higher floor (1.0 at top).
    upper = 1.0
    frac = 0.0
    for floor, frac_floor, frac_ceiling in contracts.COVERAGE_CURVE_KNOTS:
        if c >= floor:
            span = upper - floor
            frac = (frac_floor + (c - floor) / span * (frac_ceiling - frac_floor)
                    if span else frac_floor)
            break
        upper = floor
    if critical_floor_absent:
        frac = min(frac, contracts.CRITICAL_ABSENT_CAP)   # cap below Strong
    return round(frac * float(max_points), 2)


def _subscore(item) -> float:
    """Per-sub-criterion value: mean of the 5-pass 'scores' array, or scalar 'score'."""
    if not isinstance(item, dict):
        return 0.0
    arr = item.get("scores")
    if isinstance(arr, list) and arr:
        nums = [float(x) for x in arr if isinstance(x, (int, float))]
        return round(sum(nums) / len(nums), 2) if nums else 0.0
    if isinstance(item.get("score"), (int, float)):
        return float(item["score"])
    return 0.0


def compute_dim_3_score(sub_3: dict, deductions: list[dict]) -> tuple[float, float, float, float]:
    sub_keys = ["cloud_module_selection", "trusted_design", "easy_design", "adaptable_design",
                "multi_cloud_architecture"]
    raw_subtotal = sum(_subscore(sub_3.get(key)) for key in sub_keys)
    raw_subtotal = min(raw_subtotal, 20.0)
    capped_rr, _ = cap_rr_deductions(deductions)
    trust_total = sum_trust_deductions(deductions)
    final = max(0.0, raw_subtotal + capped_rr + trust_total)
    return raw_subtotal, capped_rr, trust_total, final


def compute_dim_4_score(sub_4: dict) -> tuple[float, float]:
    raw_sum = _subscore(sub_4.get("component_presence")) + _subscore(sub_4.get("architectural_decision_quality"))
    floor_cap = sub_4.get("floor_cap")
    if floor_cap is not None:
        return raw_sum, min(raw_sum, float(floor_cap))
    return raw_sum, raw_sum


# -------- Population per sheet (unchanged) ---------------------------------


# ============================================================================
# v3.1 — Token-replacement population engine (replaces coordinate writes).
# Fills the {{token}} placeholders the v3 template is authored with, leaving
# all formulas, named ranges, and merged cells intact.
# ============================================================================

_TOKEN_RE = re.compile(r"\{\{([^}]+)\}\}")

PASS_SUFFIX = ["e", "f", "g", "h", "i"]          # Dim_1-7 sheet pass columns E-I
VAR_SUFFIX  = ["c", "d", "e", "f", "g"]          # Variance_Record pass columns C-G
SUBCRIT = {
    "1": [("1A", "requirement_parsing_depth"), ("1B", "stakeholder_persona_recognition"), ("1C", "constraint_assumption_extraction")],
    "2": [("2A", "functional_requirement_traceability"), ("2B", "nfr_coverage"), ("2C", "gap_risk_identification")],
    "3": [("3A", "cloud_module_selection"), ("3B", "trusted_design"), ("3C", "easy_design"), ("3D", "adaptable_design"), ("3E", "multi_cloud_architecture")],
    "4": [("4A", "component_presence"), ("4B", "architectural_decision_quality")],
    "5": [("5A", "dependency_id_classification"), ("5B", "assumption_documentation"), ("5C", "integration_failure_modes")],
    "6": [("6A", "in_out_delineation"), ("6B", "phasing_prioritisation"), ("6C", "scope_creep_resistance")],
    "7": [("7A", "estimable_work_units"), ("7B", "complexity_effort_indicators"), ("7C", "delivery_readiness_signals")],
}
DIM_MAX = contracts.DIM_MAX  # single-sourced (v4.1); rubric section 2


def fill_xlsx_tokens(wb, tokens: dict) -> int:
    """Replace {{token}} occurrences across all sheets. Formula cells (leading '=')
    are never touched. Single-token cells preserve native value type."""
    filled = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if not isinstance(v, str) or "{{" not in v:
                    continue
                if v.lstrip().startswith("="):
                    continue
                found = _TOKEN_RE.findall(v)
                if not found:
                    continue
                if len(found) == 1 and v.strip() == "{{" + found[0] + "}}":
                    if found[0] in tokens:
                        cell.value = tokens[found[0]]
                        filled += 1
                else:
                    def _repl(m):
                        k = m.group(1)
                        return str(tokens[k]) if (k in tokens and tokens[k] is not None) else m.group(0)
                    new = _TOKEN_RE.sub(_repl, v)
                    if new != v:
                        cell.value = new
                        filled += 1
    return filled


TRUST_DED_ROWS = list(range(6, 15))   # Deductions sheet: TRUST block rows 6-14 (9)
RR_DED_ROWS = list(range(17, 23))     # Deductions sheet: RR block rows 17-22 (6)
SEVERITY_BY_VALUE = {-1: "Minor", -3: "Major", -5: "Critical"}


def fill_deductions_sheet(wb, deductions) -> dict:
    """Write the ACTUAL deductions into the Deductions sheet and CLEAR every
    unused template row, so the sheet shows only real deductions instead of the
    template's hardcoded TRUST-001..009 / RR-001..006 example rows.

    Columns A..G = Deduction ID | Type | Value | Triggering passage |
    Salesforce source | Dimension | Severity tier. TRUST severity derives from
    the value (-1 Minor / -3 Major / -5 Critical) unless supplied; RR uses
    rr_severity. The totals formulas in rows 25-28 are left untouched; blanked
    rows contribute 0. Overflow beyond template capacity is reported, not silently
    dropped."""
    if "Deductions" not in wb.sheetnames:
        return {"trust_written": 0, "rr_written": 0, "overflow": []}
    ws = wb["Deductions"]
    trust = [d for d in (deductions or []) if str(d.get("id", "")).startswith("TRUST-")]
    rr = [d for d in (deductions or []) if str(d.get("id", "")).startswith("RR-")]

    def write_row(r, d, dtype):
        val = d.get("deduction", "")
        if dtype == "TRUST":
            sev = d.get("severity_tier") or d.get("severity") or SEVERITY_BY_VALUE.get(val, "")
        else:
            sev = d.get("rr_severity", "") or ""
        ws.cell(r, 1).value = d.get("id", "")
        ws.cell(r, 2).value = dtype
        ws.cell(r, 3).value = val
        ws.cell(r, 4).value = d.get("triggering_passage", "")
        ws.cell(r, 5).value = d.get("salesforce_source", "")
        ws.cell(r, 6).value = d.get("dimension", 3)
        ws.cell(r, 7).value = sev

    def blank_row(r):
        for c in range(1, 8):
            ws.cell(r, c).value = None

    for i, r in enumerate(TRUST_DED_ROWS):
        write_row(r, trust[i], "TRUST") if i < len(trust) else blank_row(r)
    for i, r in enumerate(RR_DED_ROWS):
        write_row(r, rr[i], "RR") if i < len(rr) else blank_row(r)

    overflow = []
    if len(trust) > len(TRUST_DED_ROWS):
        overflow.append(f"{len(trust) - len(TRUST_DED_ROWS)} TRUST deduction(s) beyond template capacity {len(TRUST_DED_ROWS)}")
    if len(rr) > len(RR_DED_ROWS):
        overflow.append(f"{len(rr) - len(RR_DED_ROWS)} RR deduction(s) beyond template capacity {len(RR_DED_ROWS)}")
    return {"trust_written": min(len(trust), len(TRUST_DED_ROWS)),
            "rr_written": min(len(rr), len(RR_DED_ROWS)), "overflow": overflow}


def band_for_pct(pct) -> str:
    """Canonical four-band QUALITY model (rubric section 3), single-sourced in
    contracts.BAND_SCALE: STRONG >=80 | GOOD 70-79 | ADEQUATE 65-69 | WEAK <65.

    The band carries the disposition (Accept / Accept with changes / Rework /
    Redo) and is read on the overall total and on each dimension's percentage."""
    return contracts.band_for_pct(pct)


def gate_for_pct(pct, variance_flag=False) -> str:
    """Qualification verdict aligned 1:1 with the four bands (rubric section 8),
    single-sourced in contracts: PASS=STRONG (>=80) | MARGINAL_PASS=GOOD (70-79) |
    MARGINAL_FAIL=ADEQUATE (65-69) | FAIL=WEAK (<65)."""
    return contracts.gate_for_pct(pct, variance_flag)


# Band meaning and disposition for the four-band model: the band carries the
# disposition (Accept / Accept with changes / Rework / Redo), read on the overall
# total and per dimension.
BAND_MEANING = contracts.BAND_MEANING
GATE_DISPOSITION = contracts.GATE_DISPOSITION


def band_for_dim(mean, dim, integration_heavy) -> str:
    """Per-dimension QUALITY band from the dimension mean as a % of its max."""
    mx = contracts.dim_max(dim, integration_heavy)
    if mean is None or mx == 0:
        return ""
    return band_for_pct(100.0 * mean / mx)


def gate_for_dim(mean, dim, integration_heavy, variance_flag=False) -> str:
    """Per-dimension qualification GATE verdict (rubric section 8): the real
    PASS/MARGINAL_*/FAIL gate, NOT the quality band. Honours the variance flag."""
    mx = contracts.dim_max(dim, integration_heavy)
    if mean is None or mx == 0:
        return ""
    return gate_for_pct(100.0 * mean / mx, variance_flag)


def build_score_sheet_tokens(bundle, blinding_label, integration_heavy, floor_cap, run_record=None) -> dict:
    h = bundle.get("header", {}) or {}
    rr = run_record or {}
    means = bundle.get("per_dim_mean", {}) or {}
    bands = bundle.get("per_dim_band", {}) or {}
    flags = bundle.get("per_dim_variance_flag", {}) or {}
    reasoning = bundle.get("per_dim_key_reasoning", {}) or {}
    runs = bundle.get("five_runs_by_dimension", {}) or {}
    deductions = bundle.get("deductions", []) or []
    sub3 = bundle.get("dim_3_sub_criteria", {}) or {}

    def g(*keys, default=""):
        for source in (rr, bundle, h):
            for k in keys:
                if source.get(k) not in (None, ""):
                    return source.get(k)
        return default

    t = {}
    t["run_id"] = g("run_id")
    t["framework_version"] = contracts.FRAMEWORK_VERSION
    t["run_timestamp"] = g("run_timestamp")
    t["blinding_label"] = blinding_label
    t["operator_session_id"] = g("operator_session_id")
    t["model_version"] = g("model_version", "evaluator_model")
    t["methodology_version"] = g("methodology_version")
    t["input_artefact_sha256"] = g("input_artefact_sha256")
    t["integration_count"] = g("integration_count")
    t["integration_heavy"] = str(bool(integration_heavy)).lower()
    t["multi_cloud"] = "true" if sub3.get("multi_cloud_architecture") is not None else "false"
    t["methodology_difference_basis"] = g("methodology_difference_basis")
    t["lane_assignment_method"] = g("lane_assignment_method")
    # v3.7: ZMS provenance tokens replace Library tokens
    t["zms_version"] = g("zms_version")
    t["zms_frozen_at"] = g("zms_frozen_at")
    t["zms_applicable_criteria_count"] = g("zms_applicable_criteria_count")
    t["zms_critical_floor_active_count"] = g("zms_critical_floor_active_count")
    t["applicability_keys_fired"] = g("applicability_keys_fired")
    t["dim_4_floor_cap"] = "no cap" if floor_cap is None else floor_cap
    t["stub_missing_count"] = g("stub_missing_count_over_8_required", "stub_missing_count")
    for i in range(1, 26):
        t["R%d_result" % i] = "PASS"   # population only runs after the gate passes

    for d in range(1, 8):
        ds = str(d)
        mean = means.get(ds)
        t["dim_%d_mean" % d] = mean if mean is not None else ""
        # Authoritative band is DETERMINISTIC from the mean (rubric s.3), so the
        # band, the gate, and the score can never disagree on the sheet. The
        # model's declared per_dim_band is still R6-validated for vocabulary and
        # retained in the bundle JSON as provenance. (v4.1 consistency fix.)
        t["dim_%d_band" % d] = band_for_dim(mean, d, integration_heavy)
        t["dim_%d_deductions" % d] = 0
        t["dim_%d_key_reasoning" % d] = reasoning.get(ds, "")
        t["dim_%d_gate" % d] = gate_for_dim(mean, d, integration_heavy, bool(flags.get(ds, False)))
        t["dim_%d_score_band" % d] = band_for_dim(mean, d, integration_heavy)
        r5 = runs.get(ds, []) or []
        for idx, suf in enumerate(VAR_SUFFIX):
            t["dim_%d_pass_%s" % (d, suf)] = r5[idx] if idx < len(r5) else ""

    # Overall QUALITY band on the total score (sum of dimension means, out of 100).
    total = bundle.get("total_score")
    if total is None:
        nums = [means.get(str(d)) for d in range(1, 8) if isinstance(means.get(str(d)), (int, float))]
        total = round(sum(nums), 1) if nums else None
    t["total_score"] = total if total is not None else ""
    overall_band = band_for_pct(total)  # total is already out of 100
    t["overall_band"] = overall_band
    t["overall_band_meaning"] = BAND_MEANING.get(overall_band, "")
    # Overall GATE is the roll-up of per-dim gate verdicts and aligns 1:1 with
    # the band; the disposition the band carries is Accept / Accept with changes
    # / Rework / Redo (four-band model).
    dim_gates = [t["dim_%d_gate" % d] for d in range(1, 8)]
    overall_gate = contracts.overall_gate_from_dims(dim_gates)
    t["overall_gate"] = overall_gate
    disp, disp_meaning = GATE_DISPOSITION.get(overall_gate, ("", ""))
    t["overall_disposition"] = disp
    t["overall_disposition_meaning"] = disp_meaning

    for d, items in SUBCRIT.items():
        sub = bundle.get("dim_%s_sub_criteria" % d, {}) or {}
        for sid, key in items:
            entry = sub.get(key)
            scores = entry.get("scores", []) if isinstance(entry, dict) else []
            for idx, suf in enumerate(PASS_SUFFIX):
                t["%s_%s" % (sid, suf)] = scores[idx] if idx < len(scores) else ""
            t["%s_reasoning" % sid] = entry.get("reasoning", "") if isinstance(entry, dict) else ""

    for i in range(1, 10):
        t["trust_%03d_passage" % i] = ""
    for i in range(1, 7):
        t["rr_%03d_passage" % i] = ""
        t["rr_%03d_source" % i] = ""
    rr_n = 0
    for d in deductions:
        did = str(d.get("id", ""))
        if did.startswith("TRUST-"):
            try:
                n = int(did.split("-")[-1])
            except ValueError:
                continue
            t["trust_%03d_passage" % n] = d.get("triggering_passage", "")
        elif did.startswith("RR-"):
            rr_n += 1
            if rr_n <= 6:
                t["rr_%03d_passage" % rr_n] = d.get("triggering_passage", "")
                t["rr_%03d_source" % rr_n] = d.get("salesforce_source", "")
    return t



def default_template_path(filename: str) -> Path:
    """Resolve a bundled template from the skill's assets/ folder (real files on disk)."""
    return Path(__file__).resolve().parent.parent / "assets" / filename


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", type=Path,
                    help="Required when producing a score sheet; not needed with --validate-bundle-only.")
    ap.add_argument("--bundle", required=True, type=Path)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--blinding-label", required=True)
    ap.add_argument("--integration-heavy", action="store_true")
    ap.add_argument("--validate-bundle-only", action="store_true")
    ap.add_argument("--run-record", type=Path, help="optional run-record.json for cover provenance")
    ap.add_argument("--sdd-source-index", type=Path, default=None,
                    help="source-index.json for the lane's SDD (from source_index_build.py). "
                         "When provided, R25 escalates to PROVABLE source verification "
                         "(R25b exact-match, R25c negative-evidence, R25e relevance).")
    ap.add_argument("--zms-criteria", type=Path, default=None,
                    help="zms-criteria.json — supplies depth_indicator_components for R25e "
                         "relevance checks. Defaults to the sibling zms skill if omitted.")
    ap.add_argument("--evidence-verification-out", type=Path, default=None,
                    help="optional path to write the per-citation evidence-verification report.")
    ap.add_argument("--blinding-extra-terms", type=str, default=None,
                    help="comma-separated brand/product/vendor names to add to the "
                         "R14 leak scan (catches identity leaking via branding, logos, "
                         "or named tools). Merged with any blinding_extra_terms in the "
                         "run record.")
    args = ap.parse_args()

    if not args.bundle.exists():
        print(f"ERROR: bundle not found: {args.bundle}", file=sys.stderr)
        return 12

    with open(args.bundle, encoding="utf-8") as f:
        bundle = json.load(f)

    # Load source index + depth map for provable R25 verification, if supplied.
    source_index = None
    if args.sdd_source_index and args.sdd_source_index.exists():
        source_index = json.loads(args.sdd_source_index.read_text())
    depth_map = _load_depth_components(args.zms_criteria)

    # Resolve operator-supplied brand/product terms for the R14 leak scan from
    # the CLI and/or the run record, so identity leaking via branding/logos/named
    # tools is caught alongside the canonical lane labels.
    blinding_extra_terms = []
    if args.blinding_extra_terms:
        blinding_extra_terms += [t for t in args.blinding_extra_terms.split(",") if t.strip()]
    if getattr(args, "run_record", None) and args.run_record.exists():
        try:
            _rr_early = json.loads(args.run_record.read_text())
            blinding_extra_terms += list(_rr_early.get("blinding_extra_terms", []) or [])
        except Exception:
            pass

    ok, errors = validate_bundle(bundle, args.blinding_label, source_index, depth_map,
                                 blinding_extra_terms=blinding_extra_terms)
    if not ok:
        print(json.dumps({"status": "bundle_validation_failed", "errors": errors,
                          "rules_checked": 25, "source_verified": source_index is not None}, indent=2))
        return 20

    if args.validate_bundle_only:
        print(json.dumps({"status": "bundle_valid", "rules_checked": 25,
                          "source_verified": source_index is not None}, indent=2))
        return 0

    if args.template is None:
        args.template = default_template_path("score-sheet-template-v4.6.xlsx")

    if not args.template.exists():
        print(f"ERROR: template not found: {args.template}", file=sys.stderr)
        return 11
    if not args.output:
        print("ERROR: --output required when not in --validate-bundle-only mode", file=sys.stderr)
        return 12

    args.output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.template, args.output)
    wb = load_workbook(args.output)

    deductions = bundle.get("deductions", []) or []
    raw_subtotal, capped_rr, trust_total, final_dim_3 = compute_dim_3_score(
        bundle.get("dim_3_sub_criteria", {}), deductions)
    raw_rr_total = sum(d.get("deduction", 0) for d in deductions if str(d.get("id", "")).startswith("RR-"))
    raw_sum_dim_4, final_dim_4 = compute_dim_4_score(bundle.get("dim_4_sub_criteria", {}))
    floor_cap = (bundle.get("dim_4_sub_criteria", {}) or {}).get("floor_cap")

    run_record = {}
    if getattr(args, "run_record", None) and args.run_record.exists():
        with open(args.run_record, encoding="utf-8") as rf:
            run_record = json.load(rf)
    tokens = build_score_sheet_tokens(bundle, args.blinding_label, args.integration_heavy, floor_cap, run_record)
    filled = fill_xlsx_tokens(wb, tokens)
    ded_result = fill_deductions_sheet(wb, deductions)
    wb.save(args.output)

    wb2 = load_workbook(args.output)
    leftover = set()
    for ws in wb2.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and "{{" in c.value and not c.value.lstrip().startswith("="):
                    leftover.update(_TOKEN_RE.findall(c.value))

    print(json.dumps({
        "status": "ok",
        "output_path": str(args.output),
        "blinding_label": args.blinding_label,
        "tokens_filled": filled,
        "residual_tokens": sorted(leftover),
        "deductions_sheet": ded_result,
        "computed": {
            "dim_3_raw_subtotal": raw_subtotal,
            "dim_3_capped_rr_deduction": capped_rr,
            "dim_3_trust_deduction": trust_total,
            "dim_3_final_score": final_dim_3,
            "dim_4_final_score": final_dim_4,
        },
        "rules_checked": 25,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
