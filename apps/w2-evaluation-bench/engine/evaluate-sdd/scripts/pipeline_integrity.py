#!/usr/bin/env python3
"""
pipeline_integrity.py — fail-loud guardrails on cross-script data handoffs.

The pipeline passes JSON artifacts between stages (intake -> zms_load ->
content-map -> crosswalk -> score -> lift -> reveal -> report). Several real
defects (the empty coverage matrix, the unwired release-awareness, the gate
collapse) shipped to a live run because a handoff silently received an empty or
malformed input and produced a confident-but-hollow report instead of failing.

This module centralises the "assert the handoff is intact" checks so that a
missing or empty input HALTS or LOUDLY WARNS rather than degrading silently. It
is imported by the stage scripts; each stage declares what it must receive.

Two severities:
  - require(): a hard precondition. Raises PipelineIntegrityError -> stage halts.
  - expect():  a soft precondition. Returns a warning string (or None) the stage
               surfaces on stderr and carries into the report, never silently.
"""
from __future__ import annotations


class PipelineIntegrityError(Exception):
    """A hard handoff precondition failed; the stage must not proceed."""


def require(condition: bool, stage: str, message: str) -> None:
    """Hard precondition. Halts the stage with an actionable message."""
    if not condition:
        raise PipelineIntegrityError(f"[{stage}] HANDOFF FAILURE: {message}")


def expect(condition: bool, stage: str, message: str) -> str | None:
    """Soft precondition. Returns a warning string when violated, else None.
    The caller must surface the warning (stderr + report), never swallow it."""
    if not condition:
        return f"[{stage}] WARNING: {message}"
    return None


def nonempty_dict(obj, key=None) -> bool:
    d = obj.get(key) if (key and isinstance(obj, dict)) else obj
    return isinstance(d, dict) and len(d) > 0


def nonempty_list(obj, key=None) -> bool:
    v = obj.get(key) if (key and isinstance(obj, dict)) else obj
    return isinstance(v, list) and len(v) > 0


def check_scoring_bundle_for_report(za_bundle: dict, ots_bundle: dict, stage="report") -> list:
    """Return a list of warning strings for the report stage. Empty == clean.
    Catches the QA-02 class of failure (scoring bundles present but missing the
    content_coding the coverage matrix / IP-gap analysis are built from)."""
    warnings = []
    for name, b in (("ZA", za_bundle), ("OTS", ots_bundle)):
        if not isinstance(b, dict) or not b:
            warnings.append(f"[{stage}] WARNING: {name} scoring bundle is missing or empty; "
                            f"the report cannot build its criterion-level depth from it.")
            continue
        if not nonempty_dict(b, "content_coding"):
            warnings.append(f"[{stage}] WARNING: {name} scoring bundle has no content_coding; "
                            f"the ZMS coverage matrix, in-house IP-gap analysis, and "
                            f"per-dimension 'why' cards will be empty for this lane.")
    return warnings


def check_reveal_inputs(lift_calc: dict, zms_summary: dict,
                        za_release, ots_release, stage="reveal") -> list:
    """Soft checks for the reveal stage. Catches the QA-04 class (release-awareness
    not supplied -> empty release-currency section)."""
    warnings = []
    w = expect(nonempty_dict(lift_calc), stage, "lift-calculation input is empty; "
               "lift, gate, and uncertainty will be unavailable.")
    if w: warnings.append(w)
    w = expect(nonempty_dict(zms_summary), stage, "zms-summary input is empty; "
               "calibration provenance will be incomplete.")
    if w: warnings.append(w)
    if not (nonempty_dict(za_release) and za_release.get("findings") is not None):
        warnings.append(f"[{stage}] WARNING: ZA release-awareness was not supplied; "
                        f"the report's release-currency section will be empty for ZA. "
                        f"Pass --za-release-awareness.")
    if not (nonempty_dict(ots_release) and ots_release.get("findings") is not None):
        warnings.append(f"[{stage}] WARNING: OTS release-awareness was not supplied; "
                        f"the report's release-currency section will be empty for OTS. "
                        f"Pass --ots-release-awareness.")
    return warnings


# ---------------------------------------------------------------------------
# PER-PHASE VALIDATION GATES
#
# One gate per pipeline phase. Each returns a verdict dict:
#   {"phase","kind","status","halts":[...],"warnings":[...]}
# where:
#   - kind declares HONESTLY what the gate validates:
#       "structural"  = the artifact exists and is well-formed
#       "integrity"   = cross-phase handoff is intact (inputs the next phase needs)
#       "correctness" = an actual code-checkable correctness property holds
#                       (used ONLY where correctness is mechanically verifiable;
#                        NEVER claimed on a model-judgment phase)
#   - status is "pass" | "warn" | "halt".
#   - halts are hard postcondition failures: the phase did not produce what the
#     next phase needs; the pipeline must STOP.
#   - warnings are soft: proceed, but the report carries the caveat.
#
# A gate NEVER asserts that a model's judgment is accurate. Phases whose output
# is model judgment (content-mapping, Section D scoring) are gated only on
# STRUCTURE and INTEGRITY; their self-consistency is checked by the separate live
# verdict self-consistency check (batch 2.5) and the variance/stability machinery, which these
# gate verdicts point to rather than duplicate.
# ---------------------------------------------------------------------------

def _verdict(phase, kind, halts, warnings):
    status = "halt" if halts else ("warn" if warnings else "pass")
    return {"phase": phase, "kind": kind, "status": status,
            "halts": halts, "warnings": warnings}


def gate_intake(section_a: dict, run_record: dict) -> dict:
    """Phase 1 (intake). Structural+integrity: applicability flags derived, BRD
    SHA-256 computed, lane escrow present for Mode A. Does NOT judge SDD content."""
    halts, warns = [], []
    if not nonempty_dict(section_a):
        halts.append("[intake] no intake/section-a output produced.")
        return _verdict("intake", "structural", halts, warns)
    if not section_a.get("input_artefact_sha256"):
        halts.append("[intake] BRD SHA-256 missing; provenance/same-input proof cannot be made.")
    if "applicability_flags" not in run_record and "run_integration_heavy" not in section_a:
        warns.append("[intake] applicability flags not visible in run-record; ZMS load may under-filter.")
    rt = (section_a.get("run_type") or run_record.get("run_type") or "")
    if rt in ("comparative", "A", "mode_a") and not run_record.get("_blinding"):
        warns.append("[intake] Mode A run-record has no _blinding/escrow block; lane reveal may fail.")
    return _verdict("intake", "integrity", halts, warns)


def gate_zms_load(zms_summary: dict, calib_content: dict = None) -> dict:
    """Phase 2 (ZMS load). Structural+correctness: calibration slices written, an
    applicable-criteria count present, source split sums to the count. The source
    split is mechanically checkable -> correctness."""
    halts, warns = [], []
    if not nonempty_dict(zms_summary):
        halts.append("[zms_load] no zms-calibration-summary produced; scoring cannot calibrate.")
        return _verdict("zms_load", "structural", halts, warns)
    n = zms_summary.get("applicable_criteria_count")
    if not isinstance(n, int) or n <= 0:
        halts.append(f"[zms_load] applicable_criteria_count invalid ({n!r}).")
    by_src = zms_summary.get("criteria_by_source") or {}
    if by_src and isinstance(n, int):
        tot = sum(v for v in by_src.values() if isinstance(v, (int, float)))
        if tot != n:
            halts.append(f"[zms_load] criteria_by_source sums to {tot}, expected {n} (calibration corrupt).")
    return _verdict("zms_load", "correctness", halts, warns)


def gate_accuracy(accuracy_gate_result: dict) -> dict:
    """Phase 2.5 (verdict self-consistency check). This is the one phase that measures
    verdict-step self-consistency - agreement with the deterministic construction-rule
    labels on the validation set, NOT external accuracy. A blocking result is a hard halt."""
    halts, warns = [], []
    g = (accuracy_gate_result or {}).get("gate", accuracy_gate_result or {})
    status = g.get("status", "")
    if g.get("blocking"):
        halts.append(f"[accuracy_gate] verdict accuracy below threshold: {g.get('explanation','')}")
    elif status == "advisory":
        warns.append(f"[accuracy_gate] advisory only (validation set thin): {g.get('report_caveat','')[:160]}")
    elif status == "no_predictions":
        warns.append("[accuracy_gate] no predictions scored; verdict accuracy was not measured this run.")
    return _verdict("accuracy_gate", "correctness", halts, warns)


def gate_content_map(classify_out: dict, lane="lane") -> dict:
    """Phase 3 (content mapping). Structural only — the classification is MODEL
    JUDGMENT, so this gate verifies the artifact is well-formed (components
    present, floor-cap recorded), NOT that the classification is correct."""
    halts, warns = [], []
    if not nonempty_dict(classify_out):
        halts.append(f"[content_map:{lane}] no classification output produced.")
        return _verdict(f"content_map:{lane}", "structural", halts, warns)
    comps = classify_out.get("components") or classify_out.get("classified_components")
    if not comps:
        warns.append(f"[content_map:{lane}] no components recorded; Dim-4 floor cap may be wrong.")
    return _verdict(f"content_map:{lane}", "structural", halts, warns)


def gate_scoring_bundle(bundle: dict, lane="lane") -> dict:
    """Phase 4 (Section D scoring). Structural+integrity: the bundle must carry the
    seven dimension blocks, per-dim means, AND content_coding (needed downstream
    for the coverage matrix). The SCORES themselves are model judgment and are NOT
    judged here — R1-R25 (separate, in score_sheet_populate) checks their internal
    consistency; this gate checks the handoff is complete."""
    halts, warns = [], []
    if not nonempty_dict(bundle):
        halts.append(f"[scoring:{lane}] no scoring bundle produced.")
        return _verdict(f"scoring:{lane}", "structural", halts, warns)
    missing_dims = [d for d in range(1, 8) if f"dim_{d}_sub_criteria" not in bundle]
    if missing_dims:
        halts.append(f"[scoring:{lane}] missing dimension blocks {missing_dims}.")
    if not nonempty_dict(bundle, "per_dim_mean"):
        halts.append(f"[scoring:{lane}] per_dim_mean missing; lift/band cannot be computed.")
    if not nonempty_dict(bundle, "content_coding"):
        warns.append(f"[scoring:{lane}] no content_coding; the report's coverage matrix, "
                     f"IP-gap analysis, and 'why' cards will be empty (QA-02 class).")
    return _verdict(f"scoring:{lane}", "integrity", halts, warns)


def gate_lift(lift_calc: dict) -> dict:
    """Phase 6 (lift). Structural+correctness: both lanes' totals, the gate objects,
    and the lift metric present; the four-state gate object is well-formed."""
    halts, warns = [], []
    if not nonempty_dict(lift_calc):
        halts.append("[lift] no lift-calculation produced.")
        return _verdict("lift", "structural", halts, warns)
    for k in ("gate_pass_output_a", "gate_pass_output_b", "lift_metrics"):
        if k not in lift_calc:
            halts.append(f"[lift] missing {k}.")
    for gk in ("gate_pass_output_a", "gate_pass_output_b"):
        g = lift_calc.get(gk)
        if isinstance(g, dict) and "pass" not in g:
            halts.append(f"[lift] {gk} is malformed (no 'pass' field); gate label will be wrong.")
    return _verdict("lift", "correctness", halts, warns)


def gate_reveal(diag_bundle: dict) -> dict:
    """Phase 7 (reveal). Structural+integrity: the diagnostic bundle carries the
    cover panel with the FOUR-STATE gate, section_1 totals, and the release-
    awareness blocks. Catches the QA-01 (gate collapsed) and QA-04 (release empty)
    classes at the boundary."""
    halts, warns = [], []
    if not nonempty_dict(diag_bundle):
        halts.append("[reveal] no diagnostic bundle produced.")
        return _verdict("reveal", "structural", halts, warns)
    cp = diag_bundle.get("cover_panel") or {}
    if "gate_za" not in cp or "gate_ots" not in cp:
        halts.append("[reveal] cover_panel missing gate_za/gate_ots.")
    else:
        valid = {"PASS", "MARGINAL_PASS", "MARGINAL_FAIL", "FAIL", "", None}
        for gk in ("gate_za", "gate_ots"):
            if cp.get(gk) not in valid:
                halts.append(f"[reveal] {gk}={cp.get(gk)!r} is not a four-state gate label "
                             f"(QA-01 regression: gate must not be collapsed to binary).")
    if not nonempty_dict(diag_bundle, "section_1"):
        halts.append("[reveal] section_1 (totals/lift) missing.")
    ra = diag_bundle.get("release_awareness_a") or {}
    rb = diag_bundle.get("release_awareness_b") or {}
    if ra.get("findings") is None and rb.get("findings") is None:
        warns.append("[reveal] no release-awareness findings carried; section 5.5 will be empty (QA-04 class).")
    return _verdict("reveal", "integrity", halts, warns)


def gate_report(report_path, handoff_warnings=None) -> dict:
    """Phase 8 (report). Structural: the .docx exists and is non-trivial. Carries
    forward any handoff warnings raised while building (so a hollow report is
    flagged, not shipped silently)."""
    import os
    halts, warns = [], list(handoff_warnings or [])
    if not report_path or not os.path.exists(report_path):
        halts.append("[report] no report .docx was written.")
        return _verdict("report", "structural", halts, warns)
    if os.path.getsize(report_path) < 2000:
        warns.append("[report] report .docx is suspiciously small; it may be near-empty.")
    return _verdict("report", "structural", halts, warns)


# Ordered registry so the orchestrator (and tests) can iterate phases in sequence.
PHASE_GATES = (
    ("intake", gate_intake),
    ("zms_load", gate_zms_load),
    ("accuracy_gate", gate_accuracy),
    ("content_map", gate_content_map),
    ("scoring", gate_scoring_bundle),
    ("lift", gate_lift),
    ("reveal", gate_reveal),
    ("report", gate_report),
)


def summarize_gate(verdict: dict) -> str:
    """One-line human summary for logs/stderr."""
    tag = {"pass": "OK", "warn": "WARN", "halt": "HALT"}[verdict["status"]]
    n = len(verdict["halts"]) + len(verdict["warnings"])
    return (f"[gate:{verdict['phase']}] {tag} (kind={verdict['kind']}"
            + (f", {n} note(s)" if n else "") + ")")


def _selftest() -> int:
    ok = True
    # require raises
    try:
        require(False, "t", "boom"); print("  FAIL: require did not raise"); ok = False
    except PipelineIntegrityError:
        print("  PASS: require raises on false precondition")
    # expect returns warning then None
    if expect(False, "t", "warn") and expect(True, "t", "warn") is None:
        print("  PASS: expect returns warning on false, None on true")
    else:
        print("  FAIL: expect behaviour wrong"); ok = False
    # scoring bundle check catches missing content_coding
    w = check_scoring_bundle_for_report({"content_coding": {"1A": {}}}, {}, "t")
    if any("OTS" in x for x in w) and not any("ZA" in x for x in w):
        print("  PASS: scoring-bundle check flags the empty lane only")
    else:
        print(f"  FAIL: scoring-bundle check wrong: {w}"); ok = False
    # reveal check catches missing release-awareness
    w2 = check_reveal_inputs({"x": 1}, {"y": 1}, {"findings": []}, {}, "t")
    if any("OTS release-awareness" in x for x in w2):
        print("  PASS: reveal check flags missing release-awareness")
    else:
        print(f"  FAIL: reveal check wrong: {w2}"); ok = False

    # --- per-phase gates ---
    # intake: missing SHA halts
    v = gate_intake({"run_type": "comparative"}, {})
    if v["status"] == "halt" and any("SHA-256" in h for h in v["halts"]):
        print("  PASS: gate_intake halts on missing BRD SHA-256")
    else:
        print(f"  FAIL: gate_intake {v}"); ok = False
    # zms_load: source split mismatch halts (correctness)
    v = gate_zms_load({"applicable_criteria_count": 50, "criteria_by_source": {"Zennify": 30, "WA": 15}})
    if v["status"] == "halt" and v["kind"] == "correctness":
        print("  PASS: gate_zms_load halts when source split != count (correctness)")
    else:
        print(f"  FAIL: gate_zms_load {v}"); ok = False
    # zms_load: consistent split passes
    v = gate_zms_load({"applicable_criteria_count": 45, "criteria_by_source": {"Zennify": 30, "WA": 15}})
    if v["status"] == "pass":
        print("  PASS: gate_zms_load passes on consistent split")
    else:
        print(f"  FAIL: gate_zms_load consistent {v}"); ok = False
    # self-consistency check: blocking -> halt
    v = gate_accuracy({"gate": {"status": "block", "blocking": True, "explanation": "low"}})
    if v["status"] == "halt":
        print("  PASS: gate_accuracy halts on blocking gate")
    else:
        print(f"  FAIL: gate_accuracy {v}"); ok = False
    # scoring: missing content_coding warns (not halt) — model-judgment phase
    v = gate_scoring_bundle({**{f"dim_{d}_sub_criteria": {} for d in range(1, 8)},
                             "per_dim_mean": {"1": 3}})
    if v["status"] == "warn" and v["kind"] == "integrity" and any("content_coding" in w for w in v["warnings"]):
        print("  PASS: gate_scoring_bundle warns (not halts) on missing content_coding")
    else:
        print(f"  FAIL: gate_scoring_bundle {v}"); ok = False
    # scoring: missing a dimension halts
    v = gate_scoring_bundle({"dim_1_sub_criteria": {}, "per_dim_mean": {"1": 3}})
    if v["status"] == "halt":
        print("  PASS: gate_scoring_bundle halts on missing dimension block")
    else:
        print(f"  FAIL: gate_scoring_bundle missing-dim {v}"); ok = False
    # reveal: binary gate label (QA-01 regression) halts
    v = gate_reveal({"cover_panel": {"gate_za": "PASS", "gate_ots": "FAIL"},
                     "section_1": {"za_total": 70}})
    # 'FAIL' is a valid four-state label, so this should pass on gate labels;
    # test the collapse-detection with an invalid label:
    v_bad = gate_reveal({"cover_panel": {"gate_za": "TRUE", "gate_ots": "PASS"},
                         "section_1": {"za_total": 70}})
    if v_bad["status"] == "halt" and any("four-state" in h for h in v_bad["halts"]):
        print("  PASS: gate_reveal halts on non-four-state gate label (QA-01 guard)")
    else:
        print(f"  FAIL: gate_reveal {v_bad}"); ok = False
    # registry present
    if len(PHASE_GATES) == 8:
        print(f"  PASS: PHASE_GATES registry has all 8 phases")
    else:
        print(f"  FAIL: PHASE_GATES has {len(PHASE_GATES)}"); ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    rc = _selftest()
    print("PIPELINE-INTEGRITY SELFTEST:", "PASS" if rc == 0 else "FAIL")
    sys.exit(rc)
