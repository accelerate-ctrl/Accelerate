#!/usr/bin/env python3
"""
diagnostic_report_populate.py — Section G TOKEN LIBRARY (v4.6).

This module's role is `build_diag_tokens(bundle, za_bundle, ots_bundle)`, which
returns the validated, flattened (tokens, review_lists, expand_lists) used by the
Mode A report builder. report_build_substantive.py imports this function and
assembles the branded Diagnostic Report DIRECTLY (cover, narrative, tables, cards)
— there is no longer a .docx template to fill.

The legacy template-filling CLI (--template/--bundle/--output) was REMOVED in
v4.6; running this file as a script now fails loud and points to
report_build_substantive.py. The docx-DOM helpers further down
(fill_docx_tokens / expand_* / _trim_unused_rows / _append_score_basis_note) are
retained only as a reference implementation and are not on any shipped path.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

try:
    from docx import Document
except ImportError:
    print("ERROR: pip install python-docx --break-system-packages", file=sys.stderr)
    sys.exit(10)

_TOKEN_RE = re.compile(r"\{\{([^}]+)\}\}")

DIM_NAMES = {
    1: "BRD Comprehension", 2: "Requirement Coverage", 3: "Salesforce Solution Fit",
    4: "Design Specificity", 5: "Dependencies and Assumptions", 6: "Scope Discipline",
    7: "Estimation Readiness",
}

# Canonical sub-criterion category code frame (references/section-d-dims-*.md "Category sets
# per dimension"). For each sub-criterion key we keep a human-readable label and the
# ordered list of category names that the evaluator codes the candidate against. This
# is what makes actions specific: when content_coding.candidate_absent contains a
# category, we name it back to the methodology team verbatim.
SUB_CRITERION_FRAME = {
    "requirement_parsing_depth":          ("1A Requirement parsing", ["object", "field", "automation", "AC-to-mechanism mapping"]),
    "stakeholder_persona_recognition":    ("1B Persona recognition", ["license type", "permission-set group", "role hierarchy", "Lightning App"]),
    "constraint_assumption_extraction":   ("1C Constraint extraction", ["volume/LDV thresholds", "regulatory citations", "quantified limits"]),
    "functional_requirement_traceability": ("2A Functional traceability", ["per-AC mapping to a design element", "traceability matrix presence", "no silent omissions"]),
    "nfr_coverage":                       ("2B NFR coverage", ["performance", "security", "scalability", "compliance, each with a named SF mechanism"]),
    "gap_risk_identification":            ("2C Gap and risk", ["open-decisions log", "owner", "deadline", "impact", "status"]),
    "cloud_module_selection":             ("3A Cloud and module", ["correct cloud and edition", "platform-native first", "per-persona license analysis"]),
    "trusted_design":                     ("3B Trusted six-layer security", ["Org", "Object", "Field", "Record", "Action", "Apex"]),
    "easy_design":                        ("3C Easy (declarative-first)", ["declarative-first", "explicit Apex justification", "Dynamic Forms", "naming conventions"]),
    "adaptable_design":                   ("3D Adaptable design", ["custom metadata", "trigger framework", "Platform Events", "upgrade-safe patterns"]),
    "multi_cloud_architecture":           ("3E Multi-cloud", ["cross-cloud data flow", "identity federation", "license optimisation"]),
    "component_presence":                 ("4A Component presence", ["the 8 required components, each Substantive (no Stub/Missing)"]),
    "architectural_decision_quality":     ("4B ADR quality", ["Decision", "Context", "Options", "Rationale", "Trade-offs (per ADR)"]),
    "dependency_id_classification":       ("5A Dependency identification", ["six dependency categories", "named systems", "API version", "auth", "SLA"]),
    "assumption_documentation":           ("5B Assumptions", ["numbered", "validation plan", "owner", "consequence"]),
    "integration_failure_modes":          ("5C Integration failure modes", ["retry", "dead-letter queue", "monitoring", "idempotency (per integration)"]),
    "in_out_delineation":                 ("6A In/out scope", ["explicit scope table", "per-story binding", "exclusion rationale"]),
    "phasing_prioritisation":             ("6B Phasing", ["phases", "story-to-phase mapping", "go-live criteria"]),
    "scope_creep_resistance":             ("6C Creep resistance", ["faithful interpretation", "no gold-plating"]),
    "estimable_work_units":               ("7A Estimable work units", ["decomposed elements", "build-vs-configure distinction"]),
    "complexity_effort_indicators":       ("7B Complexity and effort", ["Simple/Moderate/Complex rating", "named basis for each"]),
    "delivery_readiness_signals":         ("7C Delivery readiness", ["deployment strategy", "environment plan", "testing approach", "data migration"]),
}

# Map sub-criterion → dimension (for filtering by source_dim)
SUB_TO_DIM = {
    "requirement_parsing_depth": 1, "stakeholder_persona_recognition": 1, "constraint_assumption_extraction": 1,
    "functional_requirement_traceability": 2, "nfr_coverage": 2, "gap_risk_identification": 2,
    "cloud_module_selection": 3, "trusted_design": 3, "easy_design": 3, "adaptable_design": 3, "multi_cloud_architecture": 3,
    "component_presence": 4, "architectural_decision_quality": 4,
    "dependency_id_classification": 5, "assumption_documentation": 5, "integration_failure_modes": 5,
    "in_out_delineation": 6, "phasing_prioritisation": 6, "scope_creep_resistance": 6,
    "estimable_work_units": 7, "complexity_effort_indicators": 7, "delivery_readiness_signals": 7,
}


def _dim_label(entry):
    sd = entry.get("source_dim")
    if isinstance(sd, int) and sd in DIM_NAMES:
        return f"Dim {sd} ({DIM_NAMES[sd]})"
    name = entry.get("dim_name")
    if isinstance(sd, int) and name:
        return f"Dim {sd} ({name})"
    if isinstance(sd, int):
        return f"Dim {sd}"
    return "this dimension"


def _resolve_category(cat_key, canonical_list):
    """Sub-criteria sometimes record positional codes (primary/secondary/tertiary).
    Resolve to the canonical category name when possible; otherwise return verbatim
    with underscores converted to spaces for readability."""
    if not isinstance(cat_key, str):
        return None
    positional = {"primary": 0, "secondary": 1, "tertiary": 2, "quaternary": 3, "quinary": 4}
    if cat_key.lower() in positional and canonical_list:
        idx = positional[cat_key.lower()]
        if idx < len(canonical_list):
            return canonical_list[idx]
        # positional reference outside the canonical list — degrade gracefully
        return f"category {idx + 1}"
    # canonical or unknown — humanise underscores
    return cat_key.replace("_", " ")


def _coding_for_sub(bundle, sub_key, sub_val):
    """Resolve the content_coding block for a sub-criterion.

    Canonical location (validated by R17/R19/R20) is the bundle's TOP-LEVEL
    `content_coding[sub_key]`; the per-sub nested block inside
    `dim_N_sub_criteria.<sub>.content_coding` is an optional mirror. Prefer the
    top-level map, fall back to the nested mirror. If the convenience lists
    (`candidate_present/partial/absent`) are absent, derive them from the
    `zms_components` verdicts so the report's gap analysis never silently
    degrades to dimension-level guidance when criterion-level evidence exists.
    """
    coding = None
    top = bundle.get("content_coding")
    if isinstance(top, dict) and isinstance(top.get(sub_key), dict):
        coding = dict(top[sub_key])
    elif isinstance(sub_val, dict) and isinstance(sub_val.get("content_coding"), dict):
        coding = dict(sub_val["content_coding"])
    if not coding:
        return {}
    comps = coding.get("zms_components") or []
    if comps and not any(coding.get(k) for k in
                         ("candidate_present", "candidate_partial", "candidate_absent")):
        derived = {"Present": [], "Partial": [], "Absent": []}
        for comp in comps:
            if not isinstance(comp, dict):
                continue
            v = comp.get("verdict")
            if v not in derived:
                continue
            label = (comp.get("zms_criterion_id") or comp.get("id") or "").strip()
            # Component-level detail is more actionable than the bare criterion id
            detail_key = {"Present": "components_present",
                          "Partial": "components_partial",
                          "Absent": "components_absent"}[v]
            details = [d for d in (comp.get(detail_key) or []) if d]
            derived[v].extend(details if details else ([label] if label else []))
        coding.setdefault("candidate_present", derived["Present"])
        coding.setdefault("candidate_partial", derived["Partial"])
        coding.setdefault("candidate_absent", derived["Absent"])
    return coding


def _gaps_for_dim(bundle, dim):
    """Walk the bundle's sub-criteria for `dim`, identify absent/partial categories,
    and return ordered (sub_label, [absent_terms], [partial_terms]) tuples."""
    if not bundle:
        return []
    sub_block = bundle.get(f"dim_{dim}_sub_criteria") or {}
    out = []
    for sub_key, sub_val in sub_block.items():
        if not isinstance(sub_val, dict):
            continue
        if SUB_TO_DIM.get(sub_key) != dim:
            continue
        coding = _coding_for_sub(bundle, sub_key, sub_val)
        if not isinstance(coding, dict):
            continue
        sub_label, canonical = SUB_CRITERION_FRAME.get(sub_key, (sub_key, []))
        absent_raw = coding.get("candidate_absent") or []
        partial_raw = coding.get("candidate_partial") or []
        absent = [_resolve_category(c, canonical) for c in absent_raw if c]
        partial = [_resolve_category(c, canonical) for c in partial_raw if c]
        if absent or partial:
            out.append((sub_label, absent, partial, coding.get("coverage")))
    return out


def _format_gap_list(gaps, max_items=3):
    """Render a compact human list of gaps suitable for embedding in the action."""
    if not gaps:
        return ""
    parts = []
    for sub_label, absent, partial, _cov in gaps[:max_items]:
        bits = []
        if absent:
            bits.append(f"missing {', '.join(absent[:4])}")
        if partial:
            bits.append(f"partial {', '.join(partial[:3])}")
        parts.append(f"{sub_label}: {'; '.join(bits)}")
    overflow = len(gaps) - max_items
    if overflow > 0:
        parts.append(f"and {overflow} further sub-criterion gap{'s' if overflow != 1 else ''}")
    return "; ".join(parts)


def _ordinalize_score(entry):
    """For Gate-fail and Methodology-underperformance, surface the actual scores."""
    parts = []
    za = entry.get("za_mean")
    ots = entry.get("ots_mean")
    margin = entry.get("baseline_margin")
    if isinstance(za, (int, float)) and isinstance(ots, (int, float)):
        parts.append(f"ZennAgent scored {za} vs off-the-shelf {ots} (gap {margin})")
    elif entry.get("notes"):
        # Gate-fail items carry "Per-dim mean X below 80% threshold Y" in notes
        parts.append(entry["notes"])
    return parts[0] if parts else ""


def recommendation_confidence(action_text: str, entry: dict, bundle=None) -> str:
    """Guardrail 4: classify whether a recommendation is substantial (evidence-
    grounded and implementable) or low-confidence (fell back to 'SA review needed'
    because the coding depth was insufficient). Reports must NOT present a generic
    'have an SA look at it' as if it were an actionable finding.

    Returns 'substantial' | 'low_confidence'.
    """
    txt = (action_text or "").lower()
    # Markers of a non-specific fallback recommendation.
    low_markers = (
        "sa review needed", "sa review recommended", "sa review will",
        "requires sa review", "did not record discrete absent",
        "side-by-side will identify", "review needed to identify",
        "review the flagged", "operator must review",
    )
    has_specific_evidence = bool(
        entry.get("notes") or entry.get("triggering_passage")
        or (bundle and _gaps_for_dim(bundle, entry.get("source_dim")))
    )
    if any(m in txt for m in low_markers) and not has_specific_evidence:
        return "low_confidence"
    return "substantial"


def action_for(entry, bundle=None):
    """Build a dimension-specific, evidence-cited, implementable recommendation.
    The action explains *why* the lane scored as it did (citing the bundle's actual
    coding evidence), *what* is missing (named categories from the canonical code
    frame), and *how* to address it (implementable items the methodology team can
    incorporate into the next refinement cycle)."""
    trigger = entry.get("issue_type", "")
    dim_lbl = _dim_label(entry)
    dim = entry.get("source_dim")
    score_line = _ordinalize_score(entry)

    # Gather sub-criterion-level evidence when bundle is available
    gaps = _gaps_for_dim(bundle, dim) if (bundle and isinstance(dim, int)) else []
    gap_text = _format_gap_list(gaps)

    # Per-trigger composition. The structure is consistently:
    #   "<Lane> failed on <Dim>: <why>. Specific gaps: <cited categories>. Address by: <implementable step>."
    if trigger == "Gate fail":
        diag = f"Quality gate fail on {dim_lbl}"
        if score_line:
            sep = "" if score_line.endswith((".", "!", "?")) else "."
            diag += f": {score_line}{sep}"
        else:
            diag += "."
        if gap_text:
            return (f"{diag} Specific gaps from coded evidence: {gap_text}. "
                    f"Address by adding the missing categories to the SDD with mechanism-level "
                    f"detail (named objects, fields, automations, or systems, not assertions).")
        return (f"{diag} Sub-criterion coding for this dimension did not record discrete absent "
                f"categories; SA review needed to identify which {DIM_NAMES.get(dim,'dimension')} "
                f"elements drove the shortfall before refinement.")

    if trigger == "Methodology underperformance":
        diag = f"ZennAgent trailed the baseline on {dim_lbl}"
        if score_line:
            sep = "" if score_line.endswith((".", "!", "?")) else "."
            diag += f": {score_line}{sep}"
        else:
            diag += "."
        if gap_text:
            return (f"{diag} The off-the-shelf SDD demonstrated categories that ZennAgent did not. "
                    f"Gaps in the ZennAgent output: {gap_text}. "
                    f"Address by updating the ZennAgent methodology prompt to require these "
                    f"categories explicitly, with worked examples anchored to the ZMS criteria the baseline demonstrated.")
        return (f"{diag} SA review of both SDDs side-by-side will identify which categories the "
                f"baseline addressed that ZennAgent did not; feed the diff into Workflow 3.")

    if trigger == "Trust deduction":
        passage = entry.get("notes") or ""
        # Truncate the passage for readability
        passage = (passage[:160] + "…") if len(passage) > 165 else passage
        return (f"Salesforce anti-pattern on {dim_lbl}. Flagged SDD passage: \u201c{passage}\u201d. "
                f"Address by replacing the anti-pattern with a Well-Architected equivalent "
                f"(Trusted > Easy > Adaptable) and updating the methodology guardrails to reject "
                f"this pattern at generation time.")

    if trigger == "Release-awareness deduction":
        passage = entry.get("notes") or ""
        passage = (passage[:160] + "…") if len(passage) > 165 else passage
        return (f"Deprecated or retired Salesforce feature recommended on {dim_lbl}. "
                f"Flagged SDD passage: \u201c{passage}\u201d. "
                f"Address by replacing with the current supported equivalent and adding a "
                f"release-awareness check to the methodology (cite current Salesforce release notes).")

    if trigger == "Variance":
        stddev = entry.get("stddev") or ""
        suffix = f" (stddev {stddev})" if stddev else ""
        return (f"Scoring instability on {dim_lbl}{suffix}: the five passes diverged, suggesting "
                f"either borderline quality or ambiguous SDD wording. SA review recommended; if "
                f"borderline, refine the methodology to produce more decisive language on this dimension.")

    if trigger == "Confidence flag":
        return (f"High-risk Confidence Annotation cited on {dim_lbl}. Operator must review the "
                f"flagged risks in the SDD's Confidence Annotations component before estimation handoff; "
                f"if the risks are real, scope and phasing should reflect them.")

    # Unknown trigger fallback
    return (f"Issue on {dim_lbl} requires SA review. " +
            (f"Coded gaps: {gap_text}. " if gap_text else "") +
            "Refer to the score sheet's deduction log and sub-criterion reasoning for context.")


def _fmt_signed(v):
    if not isinstance(v, (int, float)):
        return "" if v is None else str(v)
    return f"+{v}" if v >= 0 else str(v)


def lift_band(lift):
    if not isinstance(lift, (int, float)):
        return ""
    if lift >= 15:
        return "Strong"
    if lift >= 8:
        return "Moderate"
    if lift >= 1:
        return "Marginal"
    if lift == 0:
        return "None"
    return "Investigate"


def _fill_paragraph(p, tokens) -> int:
    if "{{" not in p.text:
        return 0
    def _repl(m):
        k = m.group(1)
        return str(tokens[k]) if (k in tokens and tokens[k] is not None) else m.group(0)
    # First pass: replace tokens that sit wholly within a single run (preserves that
    # run's formatting). This handles the common case without flattening the paragraph.
    changed = 0
    for r in p.runs:
        if "{{" in r.text:
            new_r = _TOKEN_RE.sub(_repl, r.text)
            if new_r != r.text:
                r.text = new_r
                changed = 1
    # Second pass: if a token still remains (it spanned multiple runs), collapse the
    # whole paragraph into the first run. Rare; only affects split tokens.
    if "{{" in p.text:
        new = _TOKEN_RE.sub(_repl, p.text)
        if new != p.text:
            if p.runs:
                p.runs[0].text = new
                for r in p.runs[1:]:
                    r.text = ""
            else:
                p.add_run(new)
            changed = 1
    return changed


def fill_docx_tokens(doc, tokens: dict) -> int:
    n = 0
    for p in doc.paragraphs:
        n += _fill_paragraph(p, tokens)
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    n += _fill_paragraph(p, tokens)
    return n


def _ots_context_for(za_entry, ots_bundle):
    """For a ZennAgent review item, return a short contextual line describing how
    the off-the-shelf SDD compared on the same dimension's sub-criteria. This turns
    the OTS data into *context for the ZennAgent recommendation* rather than its own
    action. Returns "" when no useful comparison can be drawn."""
    if not ots_bundle:
        return ""
    dim = za_entry.get("source_dim")
    if not isinstance(dim, int):
        return ""
    # What categories did OTS demonstrate that ZA didn't? Walk the same sub-criteria.
    sub_block = ots_bundle.get(f"dim_{dim}_sub_criteria") or {}
    ots_present_by_sub = {}
    for sub_key, sub_val in sub_block.items():
        if not isinstance(sub_val, dict):
            continue
        if SUB_TO_DIM.get(sub_key) != dim:
            continue
        coding = sub_val.get("content_coding") or {}
        if not isinstance(coding, dict):
            continue
        canonical = SUB_CRITERION_FRAME.get(sub_key, (sub_key, []))[1]
        present = [_resolve_category(c, canonical) for c in (coding.get("candidate_present") or []) if c]
        if present:
            ots_present_by_sub[sub_key] = present
    if not ots_present_by_sub:
        return ""
    # Brief: which sub-criteria did OTS cover that are relevant?
    examples = []
    for sub_key, present in list(ots_present_by_sub.items())[:2]:
        sub_label = SUB_CRITERION_FRAME.get(sub_key, (sub_key, []))[0]
        examples.append(f"{sub_label} ({', '.join(present[:3])})")
    return f" Off-the-shelf demonstrated: {'; '.join(examples)}."


def _review_rows(za_review, ots_review, priority, za_bundle=None, ots_bundle=None):
    """Compose review rows for the ZennAgent improvement actions table.

    DESIGN DECISION (v3.6): the diagnostic report's action surfaces — immediate
    actions and the SA review list — are ZennAgent-only. The off-the-shelf lane is
    a measurement baseline for calibrating lift, not a thing being improved. Its
    sub-criterion coding is used as *context* in the action text ("off-the-shelf
    demonstrated X that ZennAgent did not") but never as its own action item, and
    OTS gate-fails / variance / deductions do not appear in these tables.

    The comparison view (per-dim gap and per-dim lift tables) still shows both
    lanes — that's the legitimate calibration purpose of the off-the-shelf data."""
    rows = []
    for e in (za_review or []):
        if e.get("priority") != priority:
            continue
        trigger = e.get("issue_type", "")
        action = action_for(e, bundle=za_bundle)
        # Append OTS context only when the trigger is comparison-relevant.
        # Methodology underperformance already cites OTS scores directly; gate fail
        # benefits from seeing what the baseline covered. Other triggers don't.
        if trigger in ("Gate fail", "Methodology underperformance"):
            ots_ctx = _ots_context_for(e, ots_bundle)
            if ots_ctx:
                action = action + ots_ctx
        rows.append({
            "lane": "ZennAgent",  # always — only lane that appears in action tables
            "trigger": trigger,
            "detail": e.get("notes") or e.get("section") or "",
            "action": action,
            "confidence": recommendation_confidence(action, e, za_bundle),
        })
    return rows


def _load_zms_depth_indicators() -> dict:
    """Map criterion_id -> ZMS depth_indicator (the per-criterion quality bar).
    Used to fill the IP-gap cards' 'ZMS depth bar' with the REAL standard the
    criterion requires, instead of leaving it blank. Degrades to {} if the ZMS
    sibling cannot be resolved (the cards then omit the depth line rather than
    erroring)."""
    here = Path(__file__).resolve()
    candidates = []
    if "ZMS_SKILL_ROOT" in os.environ:
        candidates.append(Path(os.environ["ZMS_SKILL_ROOT"]))
    # scripts/ -> evaluate-sdd/ -> skills/ ; sibling zms/ is here.parent.parent.parent/zms
    candidates.append(here.parent.parent.parent / "zms")
    candidates.append(Path("/mnt/skills/user/zms"))
    candidates.append(Path("/mnt/skills/organization/zms"))
    for root in candidates:
        crit_path = root / "data" / "zms-criteria.json"
        try:
            if not crit_path.exists():
                continue
            data = json.loads(crit_path.read_text())
            items = data if isinstance(data, list) else data.get("criteria", [])
            out = {}
            for c in items:
                cid = (c.get("id") or "").strip()
                if cid:
                    out[cid] = c.get("depth_indicator", "") or ""
            if out:
                return out
        except Exception:
            continue
    return {}


def _assemble_coverage_matrix(za_bundle: dict, ots_bundle: dict) -> list:
    """QA-02: build the §5 ZMS coverage matrix by joining the two scoring
    bundles' content_coding blocks per ZMS criterion id.

    Each scoring bundle carries a top-level `content_coding` dict keyed by
    sub-criterion; each value has a `zms_components` list whose entries carry
    `zms_criterion_id`, `source_label`, `severity`, `verdict`
    (Present/Partial/Absent/NA), and `evidence_anchor`. We index both lanes by
    criterion id and emit one row per criterion, so §5 (matrix), §6 (in-house IP
    gaps = Zennify-source criteria where ZA is Partial/Absent), and the OTS-ahead
    "why" cards all have their criterion-level basis.
    """
    def _index(bundle):
        """criterion_id -> {verdict, source, severity, anchor, dim, parent_sub}"""
        out = {}
        if not isinstance(bundle, dict):
            return out
        cc = bundle.get("content_coding")
        if not isinstance(cc, dict):
            return out
        for sub_key, block in cc.items():
            if not isinstance(block, dict):
                continue
            for comp in block.get("zms_components", []) or []:
                if not isinstance(comp, dict):
                    continue
                cid = (comp.get("zms_criterion_id") or comp.get("id") or "").strip()
                if not cid:
                    continue
                # dimension is the leading digit of the criterion id (e.g. "1A.object" -> 1)
                dim = ""
                for ch in cid:
                    if ch.isdigit():
                        dim = ch
                        break
                out[cid] = {
                    "verdict": comp.get("verdict", ""),
                    "source": comp.get("source_label", comp.get("source", "")),
                    "severity": comp.get("severity", ""),
                    "anchor": comp.get("evidence_anchor", comp.get("anchor", "")),
                    "dim": dim,
                    "parent_sub": sub_key,
                }
        return out

    za_idx = _index(za_bundle)
    ots_idx = _index(ots_bundle)
    depth_map = _load_zms_depth_indicators()
    all_ids = sorted(set(za_idx) | set(ots_idx))
    matrix = []
    for cid in all_ids:
        za = za_idx.get(cid, {})
        ots = ots_idx.get(cid, {})
        ref = za or ots
        matrix.append({
            "zms_criterion_id": cid,
            "criterion_id": cid,
            "source": ref.get("source", ""),
            "severity": ref.get("severity", ""),
            "dimension": ref.get("dim", ""),
            "parent_sub_criterion": ref.get("parent_sub", ""),
            "parent_sub": ref.get("parent_sub", ""),
            "za_verdict": za.get("verdict", "—"),
            "ots_verdict": ots.get("verdict", "—"),
            "za_anchor": za.get("anchor", ""),
            "ots_anchor": ots.get("anchor", ""),
            "depth_bar": depth_map.get(cid, ""),
            "depth_indicator": depth_map.get(cid, ""),
        })
    return matrix


def build_diag_tokens(bundle: dict, za_bundle: dict = None, ots_bundle: dict = None) -> dict:
    cp = bundle.get("cover_panel", {}) or {}
    s1 = bundle.get("section_1", {}) or {}
    s11 = bundle.get("section_1_1", {}) or {}
    s2 = bundle.get("section_2", {}) or {}
    s3 = bundle.get("section_3", {}) or {}
    s4 = bundle.get("section_4_provenance", {}) or {}
    za_review = bundle.get("section_5_2_za_review", []) or []
    ots_review = bundle.get("section_5_2_ots_review", []) or []
    integration_heavy = bool(s2.get("integration_heavy", False))

    t = {}
    # headline + dashboard
    lift = s1.get("methodology_lift")
    t["methodology_lift"] = _fmt_signed(lift)
    t["lift_band"] = lift_band(lift)
    # v4.1 — lift uncertainty phrase for the dashboard. The CI/P/within-noise
    # tokens themselves are set authoritatively in the BLUF block below (single
    # source within this function); here we only build the short dashboard phrase.
    _lu = s1.get("lift_uncertainty") or {}
    if _lu:
        _lo = _lu.get("pass_noise_band_low", _lu.get("lift_ci95_low"))
        _hi = _lu.get("pass_noise_band_high", _lu.get("lift_ci95_high"))
        _pc = _lu.get("pass_correlation") or {}
        _corr_clause = ""
        if _pc:
            _corr_clause = (f"; correlation-adjusted via ICC ρ̂={_pc.get('icc_rho_hat')} "
                            f"(n_eff={_pc.get('effective_n_passes')} of {_pc.get('n_passes')} passes)")
        _blind_clause = ""
        if _pc and _pc.get("blinding_warning"):
            _blind_clause = (" — WARNING: passes show degenerate (near-identical) variance, "
                             "indicating they were not independent; treat as a single measurement")
        t["lift_uncertainty_phrase"] = (
            f"pass-noise band [{_fmt_signed(_lo)}, {_fmt_signed(_hi)}] points; "
            f"P(lift>0) = {_lu.get('p_lift_gt_0')}{_corr_clause}{_blind_clause} (pass-to-pass only; see caveat)"
        )
        t["pass_correlation_rho"] = _pc.get("icc_rho_hat", "")
        t["pass_correlation_neff"] = _pc.get("effective_n_passes", "")
        t["pass_correlation_label"] = _pc.get("reliability_label", "")
        t["pass_blinding_warning"] = _pc.get("blinding_warning", False)
        t["pass_blinding_note"] = _pc.get("blinding_note", "") or ""
    else:
        t["lift_uncertainty_phrase"] = ""
        t["pass_correlation_rho"] = ""
        t["pass_correlation_neff"] = ""
        t["pass_correlation_label"] = ""
        t["pass_blinding_warning"] = False
        t["pass_blinding_note"] = ""
    # Lift-uncertainty tokens are set later, alongside the BLUF complication clause.
    t["za_total"] = s1.get("za_total", "")
    t["ots_total"] = s1.get("ots_total", "")
    t["za_gate_overall"] = cp.get("gate_za", "")
    t["ots_gate_overall"] = cp.get("gate_ots", "")
    t["za_handoff_status"] = s11.get("za_status", cp.get("estimation_handoff_status_za", ""))
    t["ots_handoff_status"] = s11.get("ots_status", cp.get("estimation_handoff_status_ots", ""))
    t["za_handoff_basis"] = s11.get("za_basis", "")
    t["ots_handoff_basis"] = s11.get("ots_basis", "")
    t["so_what_text"] = s2.get("reading_summary", "")
    t["what_now_text"] = s3.get("reading_summary", "")

    # §2 gap table (per-dim score + gate) and §3 lift table
    rows2 = s2.get("rows", [])
    rows3 = s3.get("rows", [])
    for i in range(1, 8):
        r2 = rows2[i - 1] if i - 1 < len(rows2) else {}
        r3 = rows3[i - 1] if i - 1 < len(rows3) else {}
        za_mean, ots_mean = r2.get("za_mean"), r2.get("ots_mean")
        za_gap, ots_gap = r2.get("za_gap"), r2.get("ots_gap")
        t[f"za_dim_{i}"] = za_mean if za_mean is not None else ""
        t[f"ots_dim_{i}"] = ots_mean if ots_mean is not None else ""
        # 4-level gate from bundle when present; else derive binary from gap sign
        t[f"za_gate_{i}"] = r2.get("za_gate") or (
            "PASS" if isinstance(za_gap, (int, float)) and za_gap >= 0
            else "FAIL" if isinstance(za_gap, (int, float)) else "")
        t[f"ots_gate_{i}"] = r2.get("ots_gate") or (
            "PASS" if isinstance(ots_gap, (int, float)) and ots_gap >= 0
            else "FAIL" if isinstance(ots_gap, (int, float)) else "")
        t[f"za_{i}"] = r3.get("za_mean") if r3.get("za_mean") is not None else ""
        t[f"ots_{i}"] = r3.get("ots_mean") if r3.get("ots_mean") is not None else ""
        t[f"lift_{i}"] = _fmt_signed(r3.get("lift"))
        t[f"flag_{i}"] = "UNDERPERFORMANCE" if r3.get("underperformance") else "n/a"

    # dims 5/7 max + threshold (integration-heavy weight swap)
    if integration_heavy:
        t["d5_max"], t["d5_thr"], t["d7_max"], t["d7_thr"] = "15", "12.0", "10", "8.0"
    else:
        t["d5_max"], t["d5_thr"], t["d7_max"], t["d7_thr"] = "10", "8.0", "15", "12.0"

    # v4.1 — run-stability statement: does ZenAgent's gate/band verdict survive a
    # +/-10pp perturbation of the hand-set thresholds? Pure deterministic recompute
    # (no model calls). Lets the report state its own robustness, not just a number.
    try:
        import stability as _ssh
        za_means = {str(i): rows2[i - 1].get("za_mean") for i in range(1, 8)
                    if i - 1 < len(rows2) and isinstance(rows2[i - 1].get("za_mean"), (int, float))}
        if len(za_means) == 7:
            _stab = _ssh.gate_band_stability(za_means, integration_heavy, perturbations=(5.0, 10.0))
            t["za_stability_statement"] = _stab["summary"]
            t["za_stability_stable_10pp"] = "true" if _stab["stable_under"][10.0]["gate"] else "false"
        else:
            t["za_stability_statement"] = ""
            t["za_stability_stable_10pp"] = ""
    except Exception:
        t["za_stability_statement"] = ""
        t["za_stability_stable_10pp"] = ""

    # SA review rows (High ×3, Medium ×2, Low ×1)
    highs = _review_rows(za_review, ots_review, "High", za_bundle, ots_bundle)
    meds = _review_rows(za_review, ots_review, "Medium", za_bundle, ots_bundle)
    lows = _review_rows(za_review, ots_review, "Low", za_bundle, ots_bundle)
    for idx in range(1, 4):
        e = highs[idx - 1] if idx - 1 < len(highs) else {}
        t[f"high_{idx}_lane"] = e.get("lane", "n/a")
        t[f"high_{idx}_trigger"] = e.get("trigger", "n/a")
        t[f"high_{idx}_detail"] = e.get("detail", "n/a")
        t[f"high_{idx}_action"] = e.get("action", "n/a")
    for idx in range(1, 3):
        e = meds[idx - 1] if idx - 1 < len(meds) else {}
        t[f"med_{idx}_lane"] = e.get("lane", "n/a")
        t[f"med_{idx}_trigger"] = e.get("trigger", "n/a")
        t[f"med_{idx}_detail"] = e.get("detail", "n/a")
        t[f"med_{idx}_action"] = e.get("action", "n/a")
    e = lows[0] if lows else {}
    t["low_1_lane"] = e.get("lane", "n/a")
    t["low_1_trigger"] = e.get("trigger", "n/a")
    t["low_1_detail"] = e.get("detail", "n/a")
    t["low_1_action"] = e.get("action", "n/a")

    # provenance table (Appendix B) + header
    t["run_id"] = cp.get("run_id") or s4.get("run_id", "")
    t["run_timestamp"] = cp.get("run_timestamp", "")
    # v3.7: calibration provenance is ZMS, not the Benchmark Library. The legacy
    # token keys are retained ONLY so any not-yet-reauthored template cell fills
    # with ZMS provenance instead of a residual {{token}}; they never carry
    # Library data (which v3.7 lane_reveal_apply.py no longer emits).
    t["library_entry"] = (
        f"ZMS v{s4.get('zms_version', cp.get('zms_version', 'n/a'))} "
        f"(frozen {s4.get('zms_frozen_at', cp.get('zms_frozen_at', 'n/a'))}; "
        f"{s4.get('applicable_criteria_count', cp.get('applicable_criteria_count', 'n/a'))} criteria applicable)"
    )
    t["entry_version"] = s4.get("zms_version", cp.get("zms_version", ""))
    t["library_version"] = s4.get("zms_version", cp.get("zms_version", ""))
    t["fit_score"] = "n/a (ZMS frozen calibration, no engagement fit score)"
    t["fit_warning"] = "n/a"
    t["model_version"] = s4.get("model_version", cp.get("model_version", ""))
    t["methodology_version"] = s4.get("methodology_version", cp.get("methodology_version", ""))
    t["sha256"] = s4.get("input_artefact_sha256", "")
    t["integration_heavy"] = str(s4.get("run_integration_heavy", integration_heavy)).lower()
    t["integration_count"] = s4.get("integration_count", "")
    review_lists = {
        "High": _review_rows(za_review, ots_review, "High", za_bundle, ots_bundle),
        "Medium": _review_rows(za_review, ots_review, "Medium", za_bundle, ots_bundle),
        "Low": _review_rows(za_review, ots_review, "Low", za_bundle, ots_bundle),
    }

    # ===== v3.7 ADDITIONS =====
    # §4 Calibration Provenance — ZMS version + applicable count + source mix
    zms_summary = bundle.get("zms_calibration_summary", {}) or {}
    t["zms_version"] = zms_summary.get("zms_version", "")
    t["zms_frozen_at"] = zms_summary.get("zms_frozen_at", "")
    t["zms_applicable_count"] = zms_summary.get("applicable_criteria_count", "")
    by_source = zms_summary.get("criteria_by_source", {}) or {}
    t["zms_zen_only_count"] = by_source.get("Zennify SDD standard", 0)
    t["zms_zen_plus_wa_count"] = by_source.get("Zennify + Well-Architected", 0)
    t["zms_wa_only_count"] = by_source.get("Well-Architected", 0)
    t["zms_critical_floor_active"] = ", ".join(
        zms_summary.get("critical_floor_active", []) or []
    ) or "(none active for this engagement)"
    t["zms_applicability_keys_fired"] = ", ".join(
        zms_summary.get("applicability_keys_fired", []) or []
    ) or "(ALL only)"

    # §5 ZMS Coverage Matrix — list of dicts ready for table expansion
    # Each row: criterion_id, source, dim, parent_sub, za_verdict, ots_verdict, za_anchor, ots_anchor
    coverage_matrix = bundle.get("zms_coverage_matrix", []) or []
    # QA-02 fix: the reveal does not assemble zms_coverage_matrix, so when it is
    # empty, build it here from the two scoring bundles' content_coding blocks
    # (which ARE passed in). Without this the §5 matrix, §6 IP-gap analysis, and
    # the per-dimension "why" cards render empty even though the criterion-level
    # verdicts exist — the framework's primary product signal would be dropped.
    if not coverage_matrix and (za_bundle or ots_bundle):
        coverage_matrix = _assemble_coverage_matrix(za_bundle, ots_bundle)
    t["zms_coverage_row_count"] = len(coverage_matrix)

    # §5.5 Release Currency Audit — per-lane findings
    ra_a = bundle.get("release_awareness_a", {}) or {}
    ra_b = bundle.get("release_awareness_b", {}) or {}
    za_findings = ra_a.get("findings", []) if bundle.get("za_label") == "Output A" else ra_b.get("findings", [])
    ots_findings = ra_b.get("findings", []) if bundle.get("za_label") == "Output A" else ra_a.get("findings", [])
    # When lane mapping unknown, default to all_findings union (still useful)
    if not za_findings and not ots_findings:
        za_findings = ra_a.get("findings", []) or []
        ots_findings = ra_b.get("findings", []) or []
    t["release_findings_za_count"] = len(za_findings)
    t["release_findings_ots_count"] = len(ots_findings)
    def _is_retired(f):
        # "retired/deprecated" in the BLUF means any non-current mechanism that
        # carries an RR deduction: retired, end_of_support, or superseded. The
        # normalizer (lane_reveal_apply.normalize_release_findings) sets
        # is_noncurrent explicitly; fall back to the status taxonomy so
        # un-normalized findings are still counted correctly.
        if "is_noncurrent" in f:
            return bool(f["is_noncurrent"])
        b = f.get("status", "") or ""
        return b in ("retired", "end_of_support", "superseded")
    t["release_retired_za_count"] = sum(1 for f in za_findings if _is_retired(f))
    t["release_retired_ots_count"] = sum(1 for f in ots_findings if _is_retired(f))

    # §6 In-house IP Gap Analysis — filtered coverage matrix
    # Zennify-source criteria where ZennAgent verdict is Partial/Absent
    ip_gaps = [
        row for row in coverage_matrix
        if "Zennify" in (row.get("source") or "")
        and row.get("za_verdict") in ("Partial", "Absent")
    ]
    t["in_house_ip_gap_count"] = len(ip_gaps)
    t["in_house_ip_gap_critical_count"] = sum(
        1 for r in ip_gaps if r.get("severity") == "Critical"
    )

    # §3 Per-Dimension Lift Decomposition — lift drivers by ZMS criterion ID
    lift_drivers = bundle.get("lift_drivers_by_criterion", {}) or {}
    for dim in range(1, 8):
        drivers = lift_drivers.get(str(dim), []) or []
        t[f"lift_drivers_dim_{dim}"] = "; ".join(
            f"{d.get('zms_criterion_id', '?')} ({d.get('lift_direction', '')})"
            for d in drivers[:3]
        ) or "(no material driver)"

    # §7 Recommended Actions — six-field structure now stored on the bundle
    rec_actions = bundle.get("recommended_actions", []) or []
    t["recommended_action_count"] = len(rec_actions)
    # Guardrail 4: surface how many recommendations are low-confidence (generic
    # "SA review" fallbacks rather than evidence-grounded actions). A report whose
    # recommendations are mostly low-confidence is itself a signal that the coding
    # depth was insufficient and the findings need SA elaboration before action.
    _low = sum(1 for a in rec_actions if isinstance(a, dict)
               and a.get("confidence") == "low_confidence")
    t["recommended_action_low_confidence_count"] = _low
    t["recommended_action_substantial_count"] = len(rec_actions) - _low

    # ---- Executive Summary BLUF synthesis (grounded in run data, SCQA-shaped) ----
    # These tokens let the Executive Summary state the bottom line in words without the
    # operator hand-writing it: every value below is computed from the bundle.
    lift_val = lift if isinstance(lift, (int, float)) else 0
    za_gate = cp.get("gate_za", "") or ""
    ots_gate = cp.get("gate_ots", "") or ""
    ip_n = len(ip_gaps)
    ip_crit = sum(1 for r in ip_gaps if r.get("severity") == "Critical")
    za_ret = sum(1 for f in za_findings if _is_retired(f))
    ots_ret = sum(1 for f in ots_findings if _is_retired(f))
    applicable = zms_summary.get("applicable_criteria_count", "") or ""

    # S — Situation: what was measured, against what bar.
    t["bluf_situation"] = (
        f"Two Solution Design Documents built from the same business requirements were scored "
        f"independently and blinded against {applicable} applicable ZMS calibration criteria "
        f"(ZMS v{zms_summary.get('zms_version','4.6')}, frozen). ZenAgent scored "
        f"{s1.get('za_total','')}/100; off-the-shelf scored {s1.get('ots_total','')}/100."
    )
    # C — Complication: the lift result and what qualifies/does not.
    direction = ("a positive methodology lift" if lift_val > 0
                 else "no methodology lift" if lift_val == 0
                 else "a negative methodology lift")
    # Lift uncertainty: report the pass-noise band and P(lift>0), not a bare
    # point — and frame it honestly (it is NOT a frequentist CI; see caveat).
    lu = s1.get("lift_uncertainty") or {}
    _lo = lu.get("pass_noise_band_low", lu.get("lift_ci95_low"))
    _hi = lu.get("pass_noise_band_high", lu.get("lift_ci95_high"))
    if _lo is not None:
        within = _lo <= 0 <= _hi
        unc_clause = (
            f" Under pass-to-pass variation the lift moves within "
            f"[{_fmt_signed(_lo)} to {_fmt_signed(_hi)}] points "
            f"(P(lift>0) = {lu['p_lift_gt_0']:.2f})"
            f"{'; this spans zero, so the direction is not established even on pass noise alone' if within else ''}."
            f" This band is pass-noise only and is a LOWER BOUND on true uncertainty: "
            f"it excludes model bias and cross-session variance, so treat the lift as "
            f"directional and prefer band-level over point comparisons."
        )
        t["lift_ci95_low"] = _fmt_signed(_lo)
        t["lift_ci95_high"] = _fmt_signed(_hi)
        t["lift_pass_noise_low"] = _fmt_signed(_lo)
        t["lift_pass_noise_high"] = _fmt_signed(_hi)
        t["lift_p_gt_0"] = f"{lu['p_lift_gt_0']:.2f}"
        t["lift_within_noise"] = "true" if within else "false"
        t["lift_uncertainty_caveat"] = lu.get("uncertainty_caveat", "")
    else:
        unc_clause = ""
        t["lift_ci95_low"] = t["lift_ci95_high"] = t["lift_p_gt_0"] = ""
        t["lift_pass_noise_low"] = t["lift_pass_noise_high"] = ""
        t["lift_within_noise"] = ""
        t["lift_uncertainty_caveat"] = ""
    t["bluf_complication"] = (
        f"The ZenAgent methodology produced {direction} of {_fmt_signed(lift_val)} points "
        f"({lift_band(lift_val)}).{unc_clause} ZenAgent's qualification gate is {za_gate or 'n/a'} and "
        f"off-the-shelf's is {ots_gate or 'n/a'} at the 80% per-dimension threshold."
    )
    # Q/A — what the reader should do: the in-house IP gap signal is the product takeaway.
    if ip_n:
        t["bluf_answer"] = (
            f"{ip_n} Zennify-source criterion gap(s) were found where ZenAgent scored Partial or "
            f"Absent ({ip_crit} Critical), each a defensible, source-cited candidate for Zennify "
            f"template IP expansion. See the in-house IP gap analysis (Section 6) and the "
            f"recommended actions (Section 7)."
        )
    else:
        t["bluf_answer"] = (
            "No Zennify-source criterion gaps were found on the ZenAgent lane; the methodology "
            "covered every applicable in-house IP criterion. See the recommended actions (Section 7) "
            "for any release-currency or refinement items."
        )
    # release-currency one-liner for the summary
    t["bluf_release"] = (
        f"Release currency: {za_ret} retired/deprecated mechanism(s) named in the ZenAgent SDD and "
        f"{ots_ret} in the off-the-shelf SDD (Section 5.5)."
    )
    t["in_house_ip_gap_count_str"] = str(ip_n)
    t["release_findings_za_count_str"] = str(len(za_findings))
    t["release_findings_ots_count_str"] = str(len(ots_findings))

    # Expandable lists for table population (mirrors review_lists pattern)
    expand_lists = {
        "zms_coverage_matrix": coverage_matrix,
        "release_currency_za": za_findings,
        "release_currency_ots": ots_findings,
        "in_house_ip_gaps": ip_gaps,
        "recommended_actions": rec_actions,
    }
    return t, review_lists, expand_lists


def expand_zms_coverage_table(doc, rows):
    """Populate the ZMS Coverage Matrix table in §5.

    Expects a table whose first row header contains 'ZMS Coverage Matrix'
    or 'Criterion · Source'. Each row carries:
      - zms_criterion_id, source, dimension, parent_sub_criterion
      - za_verdict, ots_verdict, za_anchor, ots_anchor
    """
    table = _find_table_by_header(doc, ("ZMS Coverage Matrix", "ZMS Criteria",
                                         "Criterion · Source"))
    if not table:
        return 0
    fallback_row = None
    if len(table.rows) > 1:
        fallback_row = table.rows[1]
    appended = 0
    for r in rows:
        cells = [
            r.get("zms_criterion_id", ""),
            r.get("source", ""),
            f"Dim {r.get('dimension', '?')} / {r.get('parent_sub_criterion', '?')}",
            r.get("za_verdict", "n/a"),
            r.get("ots_verdict", "n/a"),
            (r.get("za_anchor", "") or "")[:120],
            (r.get("ots_anchor", "") or "")[:120],
        ]
        _append_review_row(table, cells)
        appended += 1
    _trim_unused_rows(table, appended, len(table.rows) - 1, fallback_row, trim_leading=True)
    return appended


def expand_release_currency_tables(doc, za_findings, ots_findings):
    """Populate the Release Currency Audit table in §5.5 (one section per lane)."""
    counts = {"za": 0, "ots": 0}
    for label, findings in (("ZA", za_findings), ("OTS", ots_findings)):
        table = _find_table_by_header(doc, (f"Release Currency — {label}",
                                             f"Release Awareness — {label}"))
        if not table:
            continue
        fallback_row = None
        if len(table.rows) > 1:
            fallback_row = table.rows[1]
        appended = 0
        for f in findings:
            # Field mapping bridges the release_awareness_check.py output schema
            # (mechanism_name / status / salesforce_source / source_retrieved_at /
            # supersession_recommendation) to the §5.5 columns, while still accepting
            # legacy mechanism/source_url keys if present. Status is the single
            # release-currency field (the legacy `bucket`/`classification` names are gone).
            cells = [
                f.get("finding_id", ""),
                f.get("mechanism_name", f.get("mechanism", "")),
                f.get("status", ""),
                f.get("salesforce_source", f.get("source_url", "")),
                f.get("source_retrieved_at", f.get("as_of_date", "")),
                f.get("supersession_recommendation", f.get("recommended_replacement", "n/a")),
            ]
            _append_review_row(table, cells)
            appended += 1
        _trim_unused_rows(table, appended, len(table.rows) - 1, fallback_row, trim_leading=True)
        counts[label.lower()] = appended
    return counts


def expand_in_house_ip_gap_table(doc, ip_gaps):
    """Populate the In-house IP Gap Analysis table in §6."""
    table = _find_table_by_header(doc, ("In-house IP Gap", "Zennify IP Gap",
                                         "ZennAgent IP Gap"))
    if not table:
        return 0
    fallback_row = None
    if len(table.rows) > 1:
        fallback_row = table.rows[1]
    appended = 0
    for r in ip_gaps:
        cells = [
            r.get("zms_criterion_id", ""),
            r.get("source", ""),
            r.get("severity", "n/a"),
            r.get("za_verdict", "n/a"),
            (r.get("za_anchor", "") or "What was searched: " + (
                r.get("depth_indicator", "")[:80]))[:120],
            r.get("authority_citation", ""),
        ]
        _append_review_row(table, cells)
        appended += 1
    _trim_unused_rows(table, appended, len(table.rows) - 1, fallback_row, trim_leading=True)
    return appended


def expand_recommended_actions_table(doc, actions):
    """Populate the §7 Recommended Actions table with six-field structure:
    Diagnosis · Authority · Evidence · Contrast · Required content · Where.
    """
    table = _find_table_by_header(doc, ("Recommended Actions",
                                         "Required Actions", "ZA Actions"))
    if not table:
        return 0
    fallback_row = None
    if len(table.rows) > 1:
        fallback_row = table.rows[1]
    appended = 0
    for a in actions:
        cells = [
            a.get("id", ""),
            a.get("category", ""),
            (a.get("diagnosis", "") or "")[:200],
            a.get("authority", ""),
            (a.get("evidence", "") or "")[:200],
            (a.get("contrast", "") or "")[:200],
            (a.get("required_content", "") or "")[:200],
            a.get("where", ""),
        ]
        _append_review_row(table, cells)
        appended += 1
    _trim_unused_rows(table, appended, len(table.rows) - 1, fallback_row, trim_leading=True)
    return appended


def _append_review_row(table, cells_text):
    """Append a row to a review table, copying the format of the last existing row.
    cells_text is a list of strings matching the table's column count."""
    from copy import deepcopy
    template_row = table.rows[-1]
    new_tr = deepcopy(template_row._tr)
    template_row._tr.addnext(new_tr)
    from docx.table import _Row
    new_row = _Row(new_tr, table)
    for ci, cell in enumerate(new_row.cells):
        text = cells_text[ci] if ci < len(cells_text) else ""
        # clear then set text on the first paragraph/run, preserving cell formatting
        for p in cell.paragraphs:
            for r in p.runs:
                r.text = ""
        first_p = cell.paragraphs[0]
        if first_p.runs:
            first_p.runs[0].text = text
            for r in first_p.runs[1:]:
                r.text = ""
        else:
            first_p.add_run(text)
    return new_row


def _find_table_by_header(doc, header_signature):
    """Return the first table whose header row matches header_signature.

    Two matching modes are supported (the framework uses both):

    1. Positional column match — the signature lists one substring per column,
       in order, and the table's header row has exactly that many columns with
       each substring present in the corresponding cell. Used by the review and
       provenance tables (e.g. ["priority","lane","trigger","action required"]).

    2. First-cell alternative match — the signature lists alternative labels for
       the FIRST header cell (the section's identifying label), any one of which
       may appear. Used by the v3.7 section tables, whose first header cell is the
       section name (e.g. ("ZMS Coverage Matrix", "ZMS Criteria", "Criterion · Source"))
       and whose remaining columns are free-form. This lets a wide, human-readable
       table bind without the signature having to enumerate every column.

    Mode 1 is tried first (exact, strict); if it does not match any table, mode 2
    is tried. Mode 2 only inspects the first header cell, so it cannot false-match
    on column count.
    """
    sig = [_norm_dashes(s.lower()) for s in header_signature]
    # Mode 1: positional, exact column count.
    for tb in doc.tables:
        if not tb.rows:
            continue
        hdr = [_norm_dashes(c.text.strip().lower()) for c in tb.rows[0].cells]
        if len(hdr) == len(sig) and all(sig[i] in hdr[i] for i in range(len(sig))):
            return tb
    # Mode 2: first-cell matches any alternative in the signature.
    for tb in doc.tables:
        if not tb.rows or not tb.rows[0].cells:
            continue
        first = _norm_dashes(tb.rows[0].cells[0].text.strip().lower())
        if any(alt in first for alt in sig):
            return tb
    return None


def _norm_dashes(s: str) -> str:
    """Normalise em dash (—), en dash (–), and hyphen-minus to a single hyphen so
    header matching is robust to dash style. Zennify brand content uses hyphens (em
    dashes are banned), while older signatures use em dashes; this bridges them."""
    return s.replace("\u2014", "-").replace("\u2013", "-")


def _remove_empty_row(table):
    """Remove the last data row from a docx table. Used to trim unused templated
    slots when there are fewer review items than the template provides."""
    last_row = table.rows[-1]
    last_row._tr.getparent().remove(last_row._tr)


def _trim_unused_rows(table, used_count, templated_capacity, fallback_row=None,
                      trim_leading=False):
    """If the table has more data rows than used_count, remove the unused ones.
    If used_count is 0 and a fallback row is provided, leave one row showing the
    fallback message; otherwise leave just the header. Returns rows removed.

    trim_leading=False (default, review tables): the template has `templated_capacity`
    real token slots; unused TRAILING slots are removed.

    trim_leading=True (v3.7 section tables): the template has a single placeholder
    data row and real rows are appended AFTER it; the LEADING placeholder row(s) are
    removed so only the appended real rows remain.
    """
    # row 0 is header; rows 1..templated_capacity are data slots
    data_rows = len(table.rows) - 1
    if data_rows <= used_count:
        return 0
    if used_count == 0 and fallback_row:
        # Replace the first data row with the fallback message and remove the rest
        first_data = table.rows[1]
        for ci, cell in enumerate(first_data.cells):
            text = fallback_row[ci] if ci < len(fallback_row) else ""
            for p in cell.paragraphs:
                for r in p.runs:
                    r.text = ""
            if first_data.cells[ci].paragraphs[0].runs:
                first_data.cells[ci].paragraphs[0].runs[0].text = text
            else:
                first_data.cells[ci].paragraphs[0].add_run(text)
        # remove rows 2..end
        removed = 0
        while len(table.rows) > 2:
            _remove_empty_row(table)
            removed += 1
        return removed
    # used_count > 0
    removed = 0
    if trim_leading:
        # real rows were appended AFTER the placeholder; remove leading placeholder(s)
        while (len(table.rows) - 1) > used_count and len(table.rows) > 2:
            placeholder = table.rows[1]
            placeholder._tr.getparent().remove(placeholder._tr)
            removed += 1
    else:
        # review tables: remove unused trailing token slots
        while len(table.rows) - 1 > used_count:
            _remove_empty_row(table)
            removed += 1
    return removed


def expand_review_tables(doc, review_lists):
    """Append overflow rows and trim unused rows so the action surfaces show exactly
    the items present — no silent drops, no em-dash placeholders.

    DESIGN DECISION (v3.6): the action surfaces (immediate actions + High/Med/Low SA
    review tables) are ZennAgent-only — see _review_rows docstring. This function
    expands the tables to fit all ZA items (no truncation) and trims unused slots so
    the executive doesn't see empty rows when there are fewer items than the template
    capacity. The fallback message in any empty table makes it explicit that this
    table is ZA-only and that the lane is clean on that priority."""
    appended = {"immediate_actions": 0, "High": 0, "Medium": 0, "Low": 0}
    trimmed = {"immediate_actions": 0, "High": 0, "Medium": 0, "Low": 0}

    # Immediate-actions table: Priority | Lane | Trigger | Action required (High items)
    ia = _find_table_by_header(doc, ["priority", "lane", "trigger", "action required"])
    highs = review_lists.get("High", [])
    if ia is not None:
        if len(highs) > 3:
            for e in highs[3:]:
                _append_review_row(ia, ["HIGH", e["lane"], e["trigger"], e["action"]])
                appended["immediate_actions"] += 1
        else:
            trimmed["immediate_actions"] = _trim_unused_rows(
                ia, len(highs), 3,
                fallback_row=["n/a", "ZennAgent", "No high-priority items",
                              "ZennAgent passed every dimension's qualification gate and did not trail the off-the-shelf baseline on any dimension. No immediate methodology refinement is required from this run."])

    # SA review tables: Lane | Trigger | Detail | Recommended action, one per priority.
    review_tables = []
    for tb in doc.tables:
        hdr = [c.text.strip().lower() for c in tb.rows[0].cells] if tb.rows else []
        if hdr == ["lane", "trigger", "detail", "recommended action"]:
            review_tables.append(tb)
    caps = [("High", 3), ("Medium", 2), ("Low", 1)]
    fallbacks = {
        "High": ["ZennAgent", "n/a", "No high-priority items",
                 "ZennAgent had no gate failures or material baseline gaps on this run."],
        "Medium": ["ZennAgent", "n/a", "No medium-priority items",
                   "ZennAgent had no minor methodology gaps or scoring variance on this run."],
        "Low": ["ZennAgent", "n/a", "No low-priority items",
                "No high-risk Confidence Annotations to review on this run."],
    }
    for tb, (prio, cap) in zip(review_tables, caps):
        items = review_lists.get(prio, [])
        if len(items) > cap:
            for e in items[cap:]:
                _append_review_row(tb, [e["lane"], e["trigger"], e["detail"], e["action"]])
                appended[prio] += 1
        else:
            trimmed[prio] = _trim_unused_rows(tb, len(items), cap, fallback_row=fallbacks[prio])
    return {"appended": appended, "trimmed": trimmed}


def _append_score_basis_note(doc, bundle):
    """Tweak 4: append a provenance row clarifying that the headline final score is the
    round-half-up of the summed per-dimension means, so the integer headline and the
    score-sheet TOTAL (unrounded sum of means) are reconciled for the executive reader.
    Exact and run-specific: uses the actual per-dim means from the diagnostic bundle."""
    prov = _find_table_by_header(doc, ["provenance field", "value"])
    if prov is None:
        return False
    s3 = bundle.get("section_3", {}) or {}
    rows3 = s3.get("rows", [])
    def _sum_means(side):
        vals = [r.get(f"{side}_mean") for r in rows3 if isinstance(r.get(f"{side}_mean"), (int, float))]
        return round(sum(vals), 1) if len(vals) == 7 else None
    za_sum = _sum_means("za")
    ots_sum = _sum_means("ots")
    s1 = bundle.get("section_1", {}) or {}
    za_total = s1.get("za_total")
    ots_total = s1.get("ots_total")
    parts = []
    if za_sum is not None and za_total is not None:
        parts.append(f"ZennAgent {za_total} = round-half-up of summed per-dimension means {za_sum}")
    if ots_sum is not None and ots_total is not None:
        parts.append(f"off-the-shelf {ots_total} = round-half-up of {ots_sum}")
    note = ("Headline final scores are the round-half-up of the sum of the seven "
            "per-dimension means; the score-sheet TOTAL cell shows that unrounded sum. "
            + ("; ".join(parts) + "." if parts else ""))
    _append_review_row(prov, ["score_basis", note])
    return True


def main() -> int:
    # The legacy template-filling CLI has been removed. diagnostic_report_populate
    # is now a TOKEN LIBRARY only: build_diag_tokens(...) is imported by
    # report_build_substantive.py (the Mode A Diagnostic Report builder), which
    # assembles the branded report directly and no longer fills a .docx template.
    # The docx-DOM helpers below (fill_docx_tokens / expand_* / _trim_unused_rows
    # / _append_score_basis_note) are retained only as a reference implementation
    # and are not part of any shipped path.
    sys.stderr.write(
        "diagnostic_report_populate is a token LIBRARY (build_diag_tokens), not a "
        "report builder. The legacy template-filling CLI was removed in v4.5. "
        "Use report_build_substantive.py to build the Mode A Diagnostic Report.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
