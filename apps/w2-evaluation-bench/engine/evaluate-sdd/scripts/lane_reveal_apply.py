#!/usr/bin/env python3
"""
lane_reveal_apply.py (v4.6) — boundary between Section F and Section G.

v3.7 changes (ZMS calibration substitution):
- §4 provenance and the cover panel now carry ZMS calibration provenance
  (zms_version, zms_frozen_at, applicable_criteria_count, criteria_by_source,
  critical_floor_active_count, applicability_keys_fired) sourced from
  zms-calibration-summary.json — replacing the v3.6 Benchmark Library
  provenance (library_entry / library_version / benchmark_fit_score).
- The v3.6 "Library coverage" default action is removed: ZMS is a frozen
  authored standard, not an engagement-paired exemplar, so there is no fit
  score and no "commission a new Library entry" action.
- --benchmark-profile-summary is now optional and legacy (unused under ZMS).
  --zms-summary is the v3.7 input for §4 provenance.

Reads:
  - .lane-mapping
  - lift-calc.json (Section F)
  - run-record.json (Section A/B accumulation)
  - zms-calibration-summary.json (Section B, ZMS loader output) [§4 provenance]
  - [legacy/optional] benchmark-profile-summary.json (ignored under ZMS)
  - [optional] section-5-1-actions.json (model-supplied recommended actions)

Writes:
  - diagnostic-bundle.json
  - Updated run-record.json (lane mapping recorded)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# contracts.py lives in this same scripts/ directory (single source of truth).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import contracts


def _gate_label(gate_obj, total_score):
    """Map the lift engine's four-state gate object to the rubric's four-state
    gate label (rubric s.8). The overall gate takes the WEAKEST per-dimension
    verdict (rubric s.8: "The overall gate clears (PASS) only when all seven
    dimensions are PASS; otherwise the overall result takes the weakest"), so
    it is derived from the per-dimension gates carried in the gate object —
    never from the overall total percentage. (v4.6 fix: the prior fallback to
    contracts.gate_for_pct(total) could label a lane PASS at an 80%+ total even
    though a dimension had FAILed, contradicting rubric s.8 and the lift
    engine's own `pass` flag.)

    The gate object is {pass, conditional_pass, failing_dims, marginal_dims}:
      - pass               -> PASS
      - conditional_pass   -> MARGINAL_PASS (no failing dim, but >=1 GOOD/marginal)
      - otherwise (>=1 failing dim) -> FAIL if any dimension's gate is FAIL,
        else MARGINAL_FAIL (mirrors contracts.overall_gate_from_dims).
    """
    if not isinstance(gate_obj, dict):
        return ""
    if gate_obj.get("pass"):
        return "PASS"
    if gate_obj.get("conditional_pass"):
        return "MARGINAL_PASS"
    failing = gate_obj.get("failing_dims") or []
    dim_gates = [d.get("gate") for d in failing if isinstance(d, dict)]
    if any(g == "FAIL" for g in dim_gates):
        return "FAIL"
    return "MARGINAL_FAIL"


DIM_NAMES = {
    1: "BRD Comprehension",
    2: "Requirement Coverage",
    3: "Salesforce Solution Fit",
    4: "Design Specificity",
    5: "Dependencies and Assumptions",
    6: "Scope Discipline",
    7: "Estimation Readiness",
}

UNDERPERFORMANCE_NEGATIVE_LIFT = -1.0


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_lane_mapping(raw: dict) -> dict:
    """Normalize the escrow to {label: {"origin": str, "sdd_path": str|None}}.

    v4.6 escrow schema carries the origin AND the SDD file path per label (the
    binding fix); pre-v4.6 escrows were flat {label: origin} strings. Accept
    both so historical run directories still reveal."""
    out = {}
    for label, v in (raw or {}).items():
        if isinstance(v, dict):
            out[label] = {"origin": v.get("origin"), "sdd_path": v.get("sdd_path")}
        else:
            out[label] = {"origin": v, "sdd_path": None}
    return out


def _origin(lane_mapping: dict, label: str):
    return (lane_mapping.get(label) or {}).get("origin")


# Statuses that represent a Salesforce-confirmed NOT-in-force mechanism (these
# are the "retired/deprecated" items counted in the BLUF and listed in the
# report's non-current table). Single-sourced from contracts. NOTE: this is the
# confirmed-not-in-force set ONLY — in_force_unverified is deliberately excluded
# even though it now carries a small deduction, because "could not confirm
# currency" is evidentially different from "Salesforce confirms it is gone".
RELEASE_NONCURRENT_STATUSES = frozenset(contracts.RELEASE_NOT_IN_FORCE_STATUSES)


def normalize_release_findings(ra_doc: dict) -> dict:
    """Normalize a release_crosswalk.py resolve output into a builder-friendly
    shape. The crosswalk emits per-finding keys (mechanism_name, status,
    rr_severity, salesforce_source, recommended_successor, consequence); the
    two report builders historically read a mix of those and shorter aliases
    (mechanism, severity, source, note). To keep every consumer in sync without
    editing each builder's read logic, we carry BOTH the canonical keys and the
    aliases on each finding, and flag non-current items explicitly.

    Returns a dict with a 'findings' list, preserving any other top-level keys
    from the source document. Safe on empty / missing input.
    """
    doc = dict(ra_doc or {})
    out_findings = []
    for f in (doc.get("findings") or []):
        status = f.get("status", "")
        mechanism = f.get("mechanism_name", f.get("mechanism", ""))
        severity = f.get("rr_severity", f.get("severity", ""))
        source = f.get("salesforce_source", f.get("source", f.get("source_url", "")))
        note = (f.get("recommended_successor")
                or f.get("consequence")
                or f.get("note")
                or f.get("what_to_do")
                or "")
        merged = dict(f)
        # Canonical + alias keys so both builders render fully populated rows.
        merged["status"] = status
        merged["mechanism"] = mechanism
        merged["mechanism_name"] = mechanism
        merged["severity"] = severity
        merged["rr_severity"] = severity
        merged["source"] = source
        merged["salesforce_source"] = source
        merged["note"] = note
        merged["is_noncurrent"] = status in RELEASE_NONCURRENT_STATUSES
        out_findings.append(merged)
    doc["findings"] = out_findings
    return doc


def get_threshold(dim: int, integration_heavy: bool) -> float:
    base = {1: 12.0, 2: 12.0, 3: 16.0, 4: 12.0, 5: 8.0, 6: 8.0, 7: 12.0}
    integ = {**base, 5: 12.0, 7: 8.0}
    return (integ if integration_heavy else base)[dim]


def get_max(dim: int, integration_heavy: bool) -> int:
    base = {1: 15, 2: 15, 3: 20, 4: 15, 5: 10, 6: 10, 7: 15}
    integ = {**base, 5: 15, 7: 10}
    return (integ if integration_heavy else base)[dim]


def relabel_lift_for_za(lift_calc: dict, lane_mapping: dict) -> dict:
    a_is_za = _origin(lane_mapping, "Output A") == "ZennAgent"

    output_a = lift_calc["output_a"]
    output_b = lift_calc["output_b"]
    lift_metrics = lift_calc["lift_metrics"]
    integration_heavy = lift_calc.get("integration_heavy", False)

    if a_is_za:
        za, ots = output_a, output_b
        za_score = lift_metrics["output_a_final_score"]
        ots_score = lift_metrics["output_b_final_score"]
        za_gap = lift_metrics["per_dim_gap_output_a"]
        ots_gap = lift_metrics["per_dim_gap_output_b"]
        headline = lift_metrics["headline_lift_output_a_minus_b"]
        per_dim_lift_za_ots = lift_metrics["per_dim_lift_output_a_minus_b"]
        gate_za = lift_calc["gate_pass_output_a"]
        gate_ots = lift_calc["gate_pass_output_b"]
        handoff_za = lift_calc["estimation_handoff_status_output_a"]
        handoff_ots = lift_calc["estimation_handoff_status_output_b"]
        review_za = lift_calc["priority_review_list_output_a"]
        review_ots = lift_calc["priority_review_list_output_b"]
        # uncertainty is stored A-minus-B; A is ZA here, so it is already ZA-minus-OTS
        uncertainty = (lift_metrics.get("lift_uncertainty") or None)
        if uncertainty:
            uncertainty = dict(uncertainty)
            uncertainty["orientation"] = "revealed (za_minus_ots)"
    else:
        za, ots = output_b, output_a
        za_score = lift_metrics["output_b_final_score"]
        ots_score = lift_metrics["output_a_final_score"]
        za_gap = lift_metrics["per_dim_gap_output_b"]
        ots_gap = lift_metrics["per_dim_gap_output_a"]
        headline = (-lift_metrics["headline_lift_output_a_minus_b"]
                    if lift_metrics["headline_lift_output_a_minus_b"] is not None else None)
        per_dim_lift_za_ots = {k: (-v if v is not None else None)
                                for k, v in lift_metrics["per_dim_lift_output_a_minus_b"].items()}
        gate_za = lift_calc["gate_pass_output_b"]
        gate_ots = lift_calc["gate_pass_output_a"]
        handoff_za = lift_calc["estimation_handoff_status_output_b"]
        handoff_ots = lift_calc["estimation_handoff_status_output_a"]
        review_za = lift_calc["priority_review_list_output_b"]
        review_ots = lift_calc["priority_review_list_output_a"]
        # B is ZA, so flip the A-minus-B uncertainty to ZA-minus-OTS
        import lift_calculate as _L
        uncertainty = _L.flip_uncertainty(lift_metrics.get("lift_uncertainty"))

    underperformance = {}
    for k, lift_value in per_dim_lift_za_ots.items():
        dim = int(k)
        threshold = get_threshold(dim, integration_heavy)
        za_mean = za["per_dim_mean"].get(k)
        flag = False
        if isinstance(lift_value, (int, float)) and lift_value <= UNDERPERFORMANCE_NEGATIVE_LIFT:
            flag = True
        if isinstance(za_mean, (int, float)) and za_mean < threshold:
            flag = True
        underperformance[k] = flag

    # --- Tweak 2: enrich the per-lane review items with the dimension name so the
    #     rendered "Recommended action" can name the specific dimension. The per-lane
    #     lists carry source_dim but no name (they are produced pre-reveal).
    def _enrich(review_list):
        for e in (review_list or []):
            sd = e.get("source_dim")
            if isinstance(sd, int) and sd in DIM_NAMES and "dim_name" not in e:
                e["dim_name"] = DIM_NAMES[sd]
        return review_list
    review_za = _enrich(review_za)
    review_ots = _enrich(review_ots)

    # --- Tweak 1: relative-underperformance review items (ZA below the off-the-shelf
    #     baseline on a dimension). These require the ZA-vs-OTS comparison, which only
    #     exists post-reveal, so the per-lane review list cannot contain them. We add
    #     them here and merge into review_za. Dimensions where ZA already has a
    #     gate-fail review item are not duplicated; instead that item is annotated that
    #     ZA also trails the baseline.
    gatefail_dims = {e.get("source_dim") for e in review_za
                     if e.get("issue_type") == "Gate fail" and isinstance(e.get("source_dim"), int)}
    rel_items = []
    for k, lift_value in per_dim_lift_za_ots.items():
        if not isinstance(lift_value, (int, float)) or lift_value >= 0:
            continue  # ZA met or beat the baseline on this dimension
        dim = int(k)
        za_mean = za["per_dim_mean"].get(k)
        ots_mean = ots["per_dim_mean"].get(k)
        margin = round(-lift_value, 2)  # positive number = points ZA trails OTS by
        material = lift_value <= UNDERPERFORMANCE_NEGATIVE_LIFT
        detail = (f"ZennAgent {za_mean} vs off-the-shelf {ots_mean} on "
                  f"Dim {dim} ({DIM_NAMES[dim]}); ZennAgent trails the baseline by {margin} point"
                  f"{'s' if margin != 1 else ''}.")
        if dim in gatefail_dims:
            # annotate the existing gate-fail item rather than duplicate the dimension
            for e in review_za:
                if e.get("source_dim") == dim and e.get("issue_type") == "Gate fail":
                    e["also_below_baseline"] = True
                    e["baseline_margin"] = margin
                    existing = (e.get("notes") or "").strip()
                    # ensure the prior notes end in punctuation before appending
                    if existing and not existing.endswith((".", "!", "?")):
                        existing += "."
                    e["notes"] = (
                        existing + (" " if existing else "") +
                        f"Also below the off-the-shelf baseline by {margin} "
                        f"point{'s' if margin != 1 else ''}."
                    ).strip()
            continue
        rel_items.append({
            "priority": "High" if material else "Medium",
            "section": f"Dim {dim} (below baseline)",
            "issue_type": "Methodology underperformance",
            "source_dim": dim,
            "dim_name": DIM_NAMES[dim],
            "za_mean": za_mean,
            "ots_mean": ots_mean,
            "baseline_margin": margin,
            "notes": detail,
        })
    if rel_items:
        priority_order = {"High": 0, "Medium": 1, "Low": 2}
        review_za = sorted(review_za + rel_items,
                           key=lambda e: (priority_order.get(e.get("priority"), 99),
                                          e.get("source_dim", 99)))

    # --- v4.7 dual-judge metrics (Backend Schema §9): per-judge lifts and the
    # [min, max] band reorient with the reveal exactly like the headline —
    # when Output B is ZA each judge lift negates and the band negates AND
    # swaps ends (lift_calculate.flip_judge_metrics). agreement_overall is
    # sign-agnostic and carries unchanged.
    judge_lifts = lift_metrics.get("judge_lifts_output_a_minus_b")
    lift_band = lift_metrics.get("lift_band_output_a_minus_b")
    if judge_lifts is not None and not a_is_za:
        import lift_calculate as _LJ
        _flipped = _LJ.flip_judge_metrics({
            "judge_lifts_output_a_minus_b": judge_lifts,
            "lift_band_output_a_minus_b": lift_band})
        judge_lifts = _flipped["judge_lifts_output_a_minus_b"]
        lift_band = _flipped["lift_band_output_a_minus_b"]

    return {
        "za": za, "ots": ots,
        "za_final_score": za_score, "ots_final_score": ots_score,
        "headline_lift_za_minus_ots": headline,
        "lift_uncertainty_za_minus_ots": uncertainty,
        "judge_lifts_za_minus_ots": judge_lifts,
        "lift_band_za_minus_ots": lift_band,
        "agreement_overall": lift_calc.get("agreement_overall"),
        "protocol": lift_calc.get("protocol", "five-pass"),
        "per_dim_gap_za": za_gap, "per_dim_gap_ots": ots_gap,
        "per_dim_lift_za_minus_ots": per_dim_lift_za_ots,
        "underperformance_flags_za": underperformance,
        "gate_za": gate_za, "gate_ots": gate_ots,
        "handoff_za": handoff_za, "handoff_ots": handoff_ots,
        "review_za": review_za, "review_ots": review_ots,
        "integration_heavy": integration_heavy,
    }


def generate_default_actions(revealed: dict, run_record: dict, profile_summary: dict) -> list[dict]:
    actions = []
    refinement_dims = [int(k) for k, v in revealed["underperformance_flags_za"].items() if v]
    if refinement_dims:
        dim_list = ", ".join(f"Dim {d} ({DIM_NAMES[d]})" for d in refinement_dims)
        actions.append({
            "category": "Refinement",
            "body": (f"ZennAgent underperformed on {dim_list}. Workflow 3 refinement "
                     f"recommended to close the gap. Owner: methodology lead."),
        })

    # Calibration coverage signal (v3.7 ZMS). The benchmark-fit / Library-coverage
    # action of v3.6 is removed: ZMS is a frozen authored standard, not an engagement-
    # paired exemplar, so there is no "fit score" or "commission a new entry" action.
    # Calibration provenance (version, frozen-at, applicable count) is reported in §4;
    # no action is generated here.

    headline = revealed["headline_lift_za_minus_ots"]
    if isinstance(headline, (int, float)):
        sign = "+" if headline >= 0 else ""
        actions.append({
            "category": "Informational",
            "body": (f"Methodology lift of {sign}{headline} points (ZA minus OTS) on this run. "
                     f"ZA final score {revealed['za_final_score']}/100, "
                     f"OTS final score {revealed['ots_final_score']}/100."),
        })

    actions.append({
        "category": "Escalation watch",
        "body": ("No automatic escalation triggered by this skill. The three-strike counter "
                 "is tracked manually by the methodology lead; this run's underperformance "
                 "flags should be checked against the running count."),
    })
    return actions


def build_section_4_provenance(run_record: dict, zms_summary: dict | None = None) -> dict:
    """v3.7 §4 Calibration Provenance. Same-model-by-construction design.
    Replaces the v3.6 Benchmark Library provenance (library_entry / benchmark_fit_score)
    with ZMS calibration provenance: zms_version, frozen-at, applicable criteria count,
    and source distribution. ZMS is a frozen authored standard, so there is no fit score."""
    z = zms_summary or {}
    source_dist = z.get("criteria_by_source", {}) or {}
    source_dist_str = ", ".join(f"{k}: {v}" for k, v in sorted(source_dist.items())) or "n/a"

    return {
        "run_id": run_record.get("run_id"),
        "operator_session_id": run_record.get("operator_session_id"),
        "same_input_attestation": run_record.get("same_input_attestation"),
        "same_model_attestation": run_record.get("same_model_attestation"),
        "methodology_difference_basis": run_record.get("methodology_difference_basis"),
        "model_version": run_record.get("model_version"),
        "methodology_version": run_record.get("methodology_version"),
        "rubric_version": run_record.get("rubric_version", contracts.FRAMEWORK_VERSION),
        "operations_handbook_version": run_record.get("operations_handbook_version", contracts.FRAMEWORK_VERSION),
        "framework_version": run_record.get("framework_version", contracts.FRAMEWORK_VERSION),
        "input_artefact_sha256": run_record.get("input_artefact_sha256"),
        "run_integration_heavy": str(run_record.get("run_integration_heavy", False)).lower(),
        "integration_count": run_record.get("integration_count"),
        "integration_count_basis": run_record.get("integration_count_basis"),
        # --- ZMS calibration provenance (v3.7) ---
        "zms_version": z.get("zms_version", "n/a"),
        "zms_frozen_at": z.get("zms_frozen_at", "n/a"),
        "applicable_criteria_count": z.get("applicable_criteria_count", "n/a"),
        "criteria_by_source": source_dist_str,
        "critical_floor_active_count": z.get("critical_floor_active_count", "n/a"),
        "applicability_keys_fired": ", ".join(z.get("applicability_keys_fired", []) or []) or "n/a",
    }


def four_level_gate(mean, gap, variance_flag) -> str:
    """Per-dimension gate string, aligned 1:1 with the four bands (rubric s.8):
    PASS=STRONG (>=80%), MARGINAL_PASS=GOOD (70-79%), MARGINAL_FAIL=ADEQUATE
    (65-69%), FAIL=WEAK (<65%). gap = mean - 80%-threshold, so the dimension max
    is (mean - gap) / 0.80; the gate is score-driven (single-sourced in
    contracts.gate_for_pct) and the variance flag does not move the band.
    """
    if not isinstance(mean, (int, float)) or not isinstance(gap, (int, float)):
        return ""
    threshold = mean - gap            # = GATE_PASS_FRACTION * dimension max
    if threshold <= 0:
        return ""
    mx = threshold / contracts.GATE_PASS_FRACTION
    return contracts.gate_for_pct(100.0 * mean / mx, variance_flag)


def build_diagnostic_bundle(revealed: dict, run_record: dict,
                             profile_summary: dict, actions: list[dict],
                             zms_summary: dict | None = None) -> dict:
    integration_heavy = revealed["integration_heavy"]

    section_2_rows = []
    section_3_rows = []
    for dim in range(1, 8):
        k = str(dim)
        za_mean = revealed["za"]["per_dim_mean"].get(k)
        ots_mean = revealed["ots"]["per_dim_mean"].get(k)
        za_gap = revealed["per_dim_gap_za"].get(k)
        ots_gap = revealed["per_dim_gap_ots"].get(k)
        za_vflag = revealed["za"].get("per_dim_variance_flag", {}).get(k, False)
        ots_vflag = revealed["ots"].get("per_dim_variance_flag", {}).get(k, False)
        lift = revealed["per_dim_lift_za_minus_ots"].get(k)
        underperformance = revealed["underperformance_flags_za"].get(k, False)
        section_2_rows.append({"za_mean": za_mean, "za_gap": za_gap,
                                "ots_mean": ots_mean, "ots_gap": ots_gap,
                                "za_gate": four_level_gate(za_mean, za_gap, za_vflag),
                                "ots_gate": four_level_gate(ots_mean, ots_gap, ots_vflag)})
        section_3_rows.append({"za_mean": za_mean, "ots_mean": ots_mean,
                                "lift": lift, "underperformance": underperformance})

    reading_summary_2 = build_reading_summary_section_2(revealed)
    reading_summary_3 = build_reading_summary_section_3(revealed)

    # Cover panel — v3.7 carries ZMS calibration provenance (not Library entry).
    z = zms_summary or {}

    return {
        "cover_panel": {
            "run_id": run_record.get("run_id"),
            "run_timestamp": run_record.get("run_timestamp"),
            "zms_version": z.get("zms_version", "n/a"),
            "zms_frozen_at": z.get("zms_frozen_at", "n/a"),
            "applicable_criteria_count": z.get("applicable_criteria_count", "n/a"),
            "model_version": run_record.get("model_version", ""),
            "methodology_version": run_record.get("methodology_version", ""),
            "estimation_handoff_status_za": revealed["handoff_za"]["status"],
            "estimation_handoff_status_ots": revealed["handoff_ots"]["status"],
            "gate_za": _gate_label(revealed["gate_za"], revealed.get("za_final_score")),
            "gate_ots": _gate_label(revealed["gate_ots"], revealed.get("ots_final_score")),
        },
        "section_1": {
            "za_total": revealed["za_final_score"],
            "ots_total": revealed["ots_final_score"],
            "methodology_lift": revealed["headline_lift_za_minus_ots"],
            "lift_uncertainty": revealed.get("lift_uncertainty_za_minus_ots"),
            # v4.7 dual-judge (Backend Schema §9): per-judge lifts, the
            # [min, max] band over the three lifts, and the run-level
            # cross-model agreement. None under the frozen five-pass path.
            "judge_lifts": revealed.get("judge_lifts_za_minus_ots"),
            "lift_band": revealed.get("lift_band_za_minus_ots"),
            "agreement_overall": revealed.get("agreement_overall"),
            "protocol": revealed.get("protocol", "five-pass"),
            "input_artefact_sha256": run_record.get("input_artefact_sha256"),
            "model_version": run_record.get("model_version", ""),
            "methodology_version": run_record.get("methodology_version", ""),
        },
        "section_1_1": {
            "za_status": revealed["handoff_za"]["status"],
            "za_basis": revealed["handoff_za"]["basis"],
            "ots_status": revealed["handoff_ots"]["status"],
            "ots_basis": revealed["handoff_ots"]["basis"],
        },
        "section_2": {
            "integration_heavy": integration_heavy,
            "rows": section_2_rows,
            "reading_summary": reading_summary_2,
        },
        "section_3": {
            "rows": section_3_rows,
            "reading_summary": reading_summary_3,
        },
        "section_4_provenance": build_section_4_provenance(run_record, zms_summary),
        "section_5_1_actions": actions,
        "section_5_2_za_review": revealed["review_za"],
        "section_5_2_ots_review": revealed["review_ots"],
    }


def build_reading_summary_section_2(revealed: dict) -> str:
    za_fails = sum(1 for k, gap in revealed["per_dim_gap_za"].items()
                   if isinstance(gap, (int, float)) and gap < 0)
    ots_fails = sum(1 for k, gap in revealed["per_dim_gap_ots"].items()
                    if isinstance(gap, (int, float)) and gap < 0)
    return (f"ZennAgent falls below the 80% threshold on {za_fails} of 7 dimensions; "
            f"off-the-shelf falls below on {ots_fails} of 7. Gaps are reported in points "
            f"(per-dim mean − threshold). Negative gaps indicate sub-threshold.")


def build_reading_summary_section_3(revealed: dict) -> str:
    positives, negatives = [], []
    for k, lift in revealed["per_dim_lift_za_minus_ots"].items():
        if isinstance(lift, (int, float)):
            if lift >= 1.0:
                positives.append((int(k), lift))
            elif lift <= -1.0:
                negatives.append((int(k), lift))
    parts = []
    if positives:
        positives.sort(key=lambda x: -x[1])
        parts.append(f"Methodology lift is strongest on Dim {positives[0][0]} "
                     f"({DIM_NAMES[positives[0][0]]}, +{positives[0][1]})")
    if negatives:
        negatives.sort(key=lambda x: x[1])
        parts.append(f"and weakest on Dim {negatives[0][0]} "
                     f"({DIM_NAMES[negatives[0][0]]}, {negatives[0][1]})")
    flagged = [int(k) for k, v in revealed["underperformance_flags_za"].items() if v]
    if flagged:
        parts.append(f"Underperformance flags fired on Dim(s): {flagged}, candidates for Workflow 3 refinement")
    else:
        parts.append("No underperformance flags fired; no three-strike counter advances from this run")
    return ". ".join(parts) + "."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lane-mapping", required=True, type=Path)
    ap.add_argument("--lift-calc", required=True, type=Path)
    ap.add_argument("--run-record", required=True, type=Path)
    ap.add_argument("--zms-summary", type=Path, default=None,
                    help="zms-calibration-summary.json (v3.7 §4 calibration provenance)")
    ap.add_argument("--benchmark-profile-summary", type=Path, default=None,
                    help="(legacy v3.6; optional and unused under ZMS calibration)")
    ap.add_argument("--section-5-1-actions", type=Path, default=None)
    # v4.6 (preferred): LANE-KEYED release-awareness inputs. This script is the
    # first and only reader of the escrow; requiring identity-labelled inputs
    # (the old --za/--ots flags) forced the orchestrator to know the identity
    # BEFORE the reveal ran — a circular contract that could only be satisfied
    # by peeking at the escrow or guessing. Pass the lane files as produced by
    # the crosswalk and this script maps lane -> identity internally.
    ap.add_argument("--release-awareness-a", type=Path, default=None,
                    help="Output A lane's release-awareness JSON "
                         "(release-awareness-A.json from release_crosswalk.py resolve). "
                         "Preferred over the deprecated identity-keyed flags.")
    ap.add_argument("--release-awareness-b", type=Path, default=None,
                    help="Output B lane's release-awareness JSON (release-awareness-B.json).")
    # Deprecated identity-keyed aliases (pre-v4.6): still honoured when the
    # lane-keyed flags are absent, so existing invocations keep working.
    ap.add_argument("--za-release-awareness", type=Path, default=None,
                    help="DEPRECATED (identity-keyed; requires knowing the identity pre-reveal). "
                         "Use --release-awareness-a/-b instead.")
    ap.add_argument("--ots-release-awareness", type=Path, default=None,
                    help="DEPRECATED. Use --release-awareness-a/-b instead.")
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--exec-narrative", type=Path, default=None,
                    help="JSON with the model-authored executive-summary narrative "
                         "(keys: what_we_evaluated, the_verdict, where_paid_off, "
                         "where_trailed, release_currency, confidence_caveats, "
                         "what_next). Rendered as labeled paragraphs in the report's "
                         "Executive Summary. Optional but strongly recommended — it is "
                         "what gives the report its target-quality depth.")
    args = ap.parse_args()

    lane_mapping = normalize_lane_mapping(load_json(args.lane_mapping))
    lift_calc = load_json(args.lift_calc)
    run_record = load_json(args.run_record)
    profile_summary = (load_json(args.benchmark_profile_summary)
                       if args.benchmark_profile_summary and args.benchmark_profile_summary.exists()
                       else {})
    zms_summary = (load_json(args.zms_summary)
                   if args.zms_summary and args.zms_summary.exists()
                   else {})

    actions = None
    if args.section_5_1_actions and args.section_5_1_actions.exists():
        actions = load_json(args.section_5_1_actions).get("actions", [])

    revealed = relabel_lift_for_za(lift_calc, lane_mapping)
    if not actions:
        actions = generate_default_actions(revealed, run_record, profile_summary)

    bundle = build_diagnostic_bundle(revealed, run_record, profile_summary, actions,
                                     zms_summary=zms_summary)

    # --- Release-currency findings (Section C.5 -> report Section 4) ---------
    # The crosswalk produced one release-awareness file per LANE (A/B). The
    # operator passes them in by IDENTITY (za/ots) post-reveal. Map identity
    # back to lane so build_diag_tokens (which resolves via za_label) sees the
    # findings under the lane keys it expects. Without this, the report's
    # release-currency audit is silently empty even when findings exist.
    a_is_za = _origin(lane_mapping, "Output A") == "ZennAgent"

    def _load_ra(path):
        return (normalize_release_findings(load_json(path))
                if path and path.exists() else {"findings": []})

    if args.release_awareness_a or args.release_awareness_b:
        # Preferred lane-keyed path (v4.6): no pre-reveal identity knowledge
        # needed — the escrow read above supplies the lane->identity mapping.
        bundle["release_awareness_a"] = _load_ra(args.release_awareness_a)
        bundle["release_awareness_b"] = _load_ra(args.release_awareness_b)
    else:
        # Deprecated identity-keyed path: map identity back to lane.
        za_ra = _load_ra(args.za_release_awareness)
        ots_ra = _load_ra(args.ots_release_awareness)
        if a_is_za:
            bundle["release_awareness_a"] = za_ra
            bundle["release_awareness_b"] = ots_ra
        else:
            bundle["release_awareness_a"] = ots_ra
            bundle["release_awareness_b"] = za_ra
    bundle["za_label"] = "Output A" if a_is_za else "Output B"

    run_record["_blinding"] = {
        "output_a_origin": _origin(lane_mapping, "Output A"),
        "output_b_origin": _origin(lane_mapping, "Output B"),
        "lane_revealed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
    # Model-authored executive narrative (the depth the target report shows).
    if args.exec_narrative and args.exec_narrative.exists():
        en = load_json(args.exec_narrative)
        bundle["exec_narrative"] = en.get("exec_narrative", en)
    args.run_record.write_text(json.dumps(run_record, indent=2), encoding="utf-8")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    print(json.dumps({
        "status": "ok",
        "diagnostic_bundle_path": str(args.output),
        "lane_mapping_applied": lane_mapping,
        "headline_lift_za_minus_ots": revealed["headline_lift_za_minus_ots"],
        "release_findings_za": len(bundle["release_awareness_a"]["findings"]) if a_is_za
                               else len(bundle["release_awareness_b"]["findings"]),
        "release_findings_ots": len(bundle["release_awareness_b"]["findings"]) if a_is_za
                                else len(bundle["release_awareness_a"]["findings"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
