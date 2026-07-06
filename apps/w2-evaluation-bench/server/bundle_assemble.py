"""Assemble a Mode A scoring bundle (section-d-bundle-schema, v4.6) from:
  - the five-pass aggregate (pass_accumulate.aggregate, both dim-groups),
  - per-pass verdict/coding records carried in the pass packets,
  - the narrative packet (key_reasoning / narrative / citations),
  - the ZMS calibration content, content-mapping digest, release findings,
  - run-record header fields, with attestations and truth-source strings
    injected VERBATIM from contracts (never generated).
The output must pass score_sheet_populate.validate_bundle (R1-R25) untouched.
"""
from __future__ import annotations
import json
from pathlib import Path

from .config import SCRIPTS  # noqa: F401  (ensures sys.path)
import contracts  # engine single source of truth

# Sub-criterion structure per references/section-d-bundle-schema.md.
SUBS: dict[str, list[tuple[str, int]]] = {
    "1": [("requirement_parsing_depth", 5), ("stakeholder_persona_recognition", 5),
          ("constraint_assumption_extraction", 5)],
    "2": [("functional_requirement_traceability", 5), ("nfr_coverage", 5),
          ("gap_risk_identification", 5)],
    "3": [("cloud_module_selection", 5), ("trusted_design", 5),
          ("easy_design", 5), ("adaptable_design", 5)],
    "4": [("component_presence", 9), ("architectural_decision_quality", 6)],
    "5": [("dependency_id_classification", 4), ("assumption_documentation", 3),
          ("integration_failure_modes", 3)],
    "6": [("in_out_delineation", 4), ("phasing_prioritisation", 3),
          ("scope_creep_resistance", 3)],
    "7": [("estimable_work_units", 5), ("complexity_effort_indicators", 5),
          ("delivery_readiness_signals", 5)],
}

CODE_BY_SUB: dict[str, str] = {}
SUB_ORDER: dict[str, int] = {}
for _dim, _subs in SUBS.items():
    for _i, (_k, _m) in enumerate(_subs):
        CODE_BY_SUB[_k] = f"{_dim}{chr(ord('A') + _i)}"
        SUB_ORDER[_k] = _i
CODE_BY_SUB["multi_cloud_architecture"] = "3E"


# Attestations are injected verbatim from contracts (R15/R16) - never generated.


def _band(dim: str, mean: float, integration_heavy: bool) -> str:
    mx = contracts.dim_max(int(dim), integration_heavy)
    return contracts.band_for_pct(100.0 * mean / mx)


def assemble(*, run_id: str, label: str, aggregate: dict, pass_results: list[dict],
             narrative: dict, calibration: dict, mapping: dict, release: dict,
             run_record: dict, multi_cloud: bool = False) -> dict:
    integration_heavy = bool(run_record.get("run_integration_heavy")
                             or run_record.get("integration_heavy"))
    runs = aggregate["five_runs_by_dimension"]
    means = aggregate["per_dim_mean"]
    stddevs = aggregate["per_dim_stddev"]
    flags = aggregate["per_dim_variance_flag"]
    sub_arrays = aggregate.get("sub_score_arrays", {})
    modal = aggregate.get("modal_verdicts", {})

    # --- coding: per criterion pick the record from a pass matching the modal verdict
    per_crit: dict[str, dict] = {}
    for pr in pass_results:
        for cid, rec in (pr.get("verdicts") or {}).items():
            want = modal.get(cid)
            if cid not in per_crit and (want is None or rec.get("verdict") == want):
                per_crit[cid] = rec
    for pr in pass_results:  # backstop: any record at all
        for cid, rec in (pr.get("verdicts") or {}).items():
            per_crit.setdefault(cid, rec)

    crits = calibration["applicable_criteria"]
    coding: dict[str, dict] = {}
    sub_key_by_parent = {}
    for dim, subs in SUBS.items():
        for i, (k, _mx) in enumerate(subs):
            sub_key_by_parent[f"{dim}{chr(ord('A') + i)}"] = k
    # dim3 multi-cloud sub (3E)
    if multi_cloud:
        sub_key_by_parent["3E"] = "multi_cloud_architecture"

    for c in crits:
        cid = c["id"]
        parent = c.get("parent_sub_criterion") or cid.split(".")[0]
        sub_key = sub_key_by_parent.get(parent, parent)
        rec = per_crit.get(cid, {})
        verdict = rec.get("verdict") or modal.get(cid) or "NA"
        entry = {
            "zms_criterion_id": cid,
            "source_label": c.get("source_label") or c.get("source") or "Zennify SDD standard",
            "severity": c.get("severity", ""),
            "verdict": verdict,
            "evidence_anchor": rec.get("evidence_anchor")
                               or ("topic absent from SDD" if verdict == "Absent" else ""),
            "sdd_ref": rec.get("sdd_ref", ""),
            "components_present": rec.get("components_present", []),
            "components_partial": rec.get("components_partial", []),
            "components_absent": rec.get("components_absent", []),
        }
        blk = coding.setdefault(sub_key, {"zms_components": [], "candidate_present": [],
                                          "candidate_partial": [], "candidate_absent": []})
        blk["zms_components"].append(entry)
        blk["candidate_present"] += entry["components_present"]
        blk["candidate_partial"] += entry["components_partial"]
        blk["candidate_absent"] += entry["components_absent"]
    for blk in coding.values():
        comps = blk["zms_components"]
        score = sum(1.0 if e["verdict"] == "Present" else 0.5 if e["verdict"] == "Partial" else 0.0
                    for e in comps if e["verdict"] != "NA")
        n = sum(1 for e in comps if e["verdict"] != "NA") or 1
        blk["coverage"] = round(score / n, 2)
        for k in ("candidate_present", "candidate_partial", "candidate_absent"):
            blk[k] = sorted(set(blk[k]))

    # --- dim_N_sub_criteria blocks
    def sub_block(dim: str) -> dict:
        out = {}
        for key, mx in SUBS[dim]:
            code = CODE_BY_SUB.get(key)
            arr = (sub_arrays.get(code) if isinstance(sub_arrays.get(code), list)
                   else (sub_arrays.get(dim, {}) or {}).get(key)
                   if isinstance(sub_arrays.get(dim), dict) else None)
            if not arr:
                m = means[dim] / contracts.dim_max(int(dim), integration_heavy)
                arr = [round(m * mx, 1)] * 5
            cov = coding.get(key, {})
            reasoning = (f"Five-pass sub-criterion result for {key.replace('_', ' ')} "
                         f"(coverage {cov.get('coverage', 'n/a')}): "
                         + "; ".join(e["zms_criterion_id"] + "=" + e["verdict"]
                                     for e in cov.get("zms_components", [])[:4]))
            if len(reasoning) < 60:
                reasoning += ". Derived from the five independent pass scores recorded for this sub-criterion."
            out[key] = {"scores": [round(float(x), 1) for x in arr][:5],
                        "max": mx, "reasoning": reasoning,
                        "content_coding": cov or {"zms_components": [], "candidate_present": [],
                                                  "candidate_partial": [], "candidate_absent": [],
                                                  "coverage": 0.0}}
        return out

    d3 = sub_block("3")
    d3["multi_cloud_architecture"] = None if not multi_cloud else sub_block("3").get(
        "multi_cloud_architecture")
    d4 = sub_block("4")
    d4["floor_cap"] = mapping.get("dim_4_floor_cap")
    raw4 = round(sum(d4[k]["scores"][-1] for k in ("component_presence",
                                                   "architectural_decision_quality")), 1)
    d4["raw_sum_before_floor"] = raw4
    cap = d4["floor_cap"]
    d4["final_dim_4_score"] = min(raw4, cap) if cap is not None else raw4

    # --- deductions from release findings (RR only; TRUST empty unless supplied)
    deductions = []
    rr_findings = []
    for i, f in enumerate((release.get("findings") or []), 1):
        src = f.get("salesforce_source") or f.get("source_url") or ""
        if not src:
            # R23: the bundle's finding table only carries source-cited findings;
            # unverified/no-source mechanisms stay in the release file for the
            # report appendix but cannot ground a deduction or a bundle row.
            continue
        rr_findings.append({"finding_id": f.get("finding_id", f"RR-X-{i:03d}"),
                            "mechanism_name": f.get("mechanism_name") or f.get("mechanism", ""),
                            "status": f.get("status", ""),
                            "source_url": src,
                            "salesforce_source": src})
        ded = f.get("rr_deduction", 0)
        if ded:
            deductions.append({
                "id": f"RR-{i:03d}",
                "source": "Release-awareness finding (release-awareness-{a|b}.json)",
                "release_finding_ref": rr_findings[-1]["finding_id"],
                "deduction": ded,
                "triggering_passage": (f.get("triggering_passage") or f.get("evidence_note")
                                       or f'{rr_findings[-1]["mechanism_name"]} named in the SDD'),
                "salesforce_source": f.get("salesforce_source", ""),
                "rr_severity": f.get("rr_severity") or "Major",
                "rationale": f.get("consequence") or f.get("rationale")
                             or f'{rr_findings[-1]["mechanism_name"]}: {f.get("status", "")}.',
            })

    bundle = {
        "run_id": run_id,
        "blinding_label": label,
        "header": {
            "zms_version": calibration.get("zms_version"),
            "zms_frozen_at": calibration.get("zms_frozen_at"),
            "evaluator_model": run_record.get("evaluator_model_version")
                               or run_record.get("evaluator_model") or run_record.get("model_version"),
            "model_version": run_record.get("model_version"),
            "methodology_version": run_record.get("methodology_version"),
        },
        "five_runs_by_dimension": {k: [round(float(x), 1) for x in runs[k]] for k in map(str, range(1, 8))},
        "dim_1_sub_criteria": sub_block("1"),
        "dim_2_sub_criteria": sub_block("2"),
        "dim_3_sub_criteria": d3,
        "dim_4_sub_criteria": d4,
        "dim_5_sub_criteria": sub_block("5"),
        "dim_6_sub_criteria": sub_block("6"),
        "dim_7_sub_criteria": sub_block("7"),
        "deductions": deductions,
        "per_dim_band": {d: _band(d, float(means[d]), integration_heavy) for d in map(str, range(1, 8))},
        "per_dim_mean": {d: round(float(means[d]), 1) for d in map(str, range(1, 8))},
        "per_dim_stddev": {d: round(float(stddevs[d]), 2) for d in map(str, range(1, 8))},
        "per_dim_variance_flag": {d: bool(flags[d]) for d in map(str, range(1, 8))},
        "per_dim_truth_source": dict(contracts.EXPECTED_TRUTH_SOURCE),
        "per_dim_key_reasoning": narrative["per_dim_key_reasoning"],
        "narrative_per_dim": narrative["narrative_per_dim"],
        "zms_calibration_citations": narrative["zms_calibration_citations"],
        "zms_calibration": {"applicable_criteria": crits},
        "content_coding": coding,
        "release_awareness_findings": rr_findings,
        "confidence_annotations_high_risk": bool(mapping.get("confidence_annotations_high_risk")),
        "blinding_attestation": contracts.BLINDING_ATTESTATION,
        "non_bias_attestation": contracts.NON_BIAS_ATTESTATION,
    }
    return bundle


# ===========================================================================
# v4.7 — DUAL-JUDGE CONSENSUS BUNDLE (Backend Schema §7). The v4.6 assemble()
# above is FROZEN for EVAL_PROTOCOL=five-pass. Everything the v4.6 bundle
# carried is carried here too — content_coding, zms_calibration_citations,
# deductions, truth sources, release findings, attestations — nothing is
# reduced; the five-pass statistics are REPLACED by the judge/consensus/
# agreement fields, and the reconcile audit trail (provenance, judge_entries,
# ruling citations, dissents) is added (errata Q7).
# ===========================================================================

def assemble_v47(*, run_id: str, label: str, aggregate: dict,
                 agreement_stats: dict, narrative: dict, calibration: dict,
                 mapping: dict, release: dict, run_record: dict,
                 judge_models: dict | None = None,
                 multi_cloud: bool = False) -> dict:
    """Assemble the v4.7 scoring bundle from judge_accumulate.aggregate()'s
    lane aggregate + the lane-level agreement stats (consensus.merge_lane_stats)
    + the narrative packet. Must pass validate_bundle_v47 (R1, R3–R28)."""
    ja, jb = contracts.JUDGES
    integration_heavy = bool(run_record.get("run_integration_heavy")
                             or run_record.get("integration_heavy"))
    means = aggregate["per_dim_mean"]
    bands = aggregate["per_dim_band"]
    sub_scores = aggregate["sub_scores"]          # {dim: {key: {ja, jb, consensus, provenance}}}
    cons_verdicts = aggregate["consensus_verdicts"]
    cons_prov = aggregate["consensus_provenance"]
    judge_entries = aggregate.get("judge_entries", {})
    ruling_citations = aggregate.get("ruling_citations", {})
    ruling_rationales = aggregate.get("ruling_rationales", {})

    # --- content coding from CONSENSUS verdicts (+ reconcile audit trail)
    crits = calibration["applicable_criteria"]
    sub_key_by_parent = {}
    for dim, subs in SUBS.items():
        for i, (k, _mx) in enumerate(subs):
            sub_key_by_parent[f"{dim}{chr(ord('A') + i)}"] = k
    if multi_cloud:
        sub_key_by_parent["3E"] = "multi_cloud_architecture"

    coding: dict[str, dict] = {}
    for c in crits:
        cid = c["id"]
        parent = c.get("parent_sub_criterion") or cid.split(".")[0]
        sub_key = sub_key_by_parent.get(parent, parent)
        rec = cons_verdicts.get(cid) or {}
        verdict = rec.get("verdict") or "NA"
        entry = {
            "zms_criterion_id": cid,
            "source_label": c.get("source_label") or c.get("source") or "Zennify SDD standard",
            "severity": c.get("severity", ""),
            "verdict": verdict,
            "evidence_anchor": rec.get("evidence_anchor")
                               or ("topic absent from SDD" if verdict == "Absent" else ""),
            "sdd_ref": rec.get("sdd_ref", ""),
            "components_present": rec.get("components_present", []),
            "components_partial": rec.get("components_partial", []),
            "components_absent": rec.get("components_absent", []),
            "provenance": cons_prov.get(cid, "agreed"),
        }
        if cid in judge_entries and judge_entries[cid]:
            entry["judge_entries"] = judge_entries[cid]
        if cid in ruling_citations:
            entry["ruling_citation"] = ruling_citations[cid]
        if cid in ruling_rationales:
            entry["ruling_rationale"] = ruling_rationales[cid]
        blk = coding.setdefault(sub_key, {"zms_components": [], "candidate_present": [],
                                          "candidate_partial": [], "candidate_absent": []})
        blk["zms_components"].append(entry)
        blk["candidate_present"] += entry["components_present"]
        blk["candidate_partial"] += entry["components_partial"]
        blk["candidate_absent"] += entry["components_absent"]
    for blk in coding.values():
        comps = blk["zms_components"]
        score = sum(1.0 if e["verdict"] == "Present" else 0.5 if e["verdict"] == "Partial" else 0.0
                    for e in comps if e["verdict"] != "NA")
        n = sum(1 for e in comps if e["verdict"] != "NA") or 1
        blk["coverage"] = round(score / n, 2)
        for k in ("candidate_present", "candidate_partial", "candidate_absent"):
            blk[k] = sorted(set(blk[k]))

    # --- dim_N_sub_criteria: three-key entries + provenance (+ v4.6 detail)
    def sub_block(dim: str) -> dict:
        out = {}
        for key, mx in SUBS[dim]:
            tk = (sub_scores.get(dim) or {}).get(key) or {}
            cov = coding.get(key, {})
            prov = tk.get("provenance", "agreed")
            reasoning = (f"Dual-judge consensus for {key.replace('_', ' ')} "
                         f"(provenance {prov}; coverage {cov.get('coverage', 'n/a')}): "
                         + "; ".join(e["zms_criterion_id"] + "=" + e["verdict"]
                                     for e in cov.get("zms_components", [])[:4]))
            if len(reasoning) < 60:
                reasoning += (". Derived from the two independent judge scores "
                              "recorded for this sub-criterion.")
            out[key] = {ja: tk.get(ja), jb: tk.get(jb),
                        "consensus": tk.get("consensus"),
                        "provenance": prov,
                        "max": mx, "reasoning": reasoning,
                        "content_coding": cov or {"zms_components": [], "candidate_present": [],
                                                  "candidate_partial": [], "candidate_absent": [],
                                                  "coverage": 0.0}}
        return out

    d3 = sub_block("3")
    if not multi_cloud:
        d3["multi_cloud_architecture"] = None
    d4 = sub_block("4")
    d4["floor_cap"] = mapping.get("dim_4_floor_cap")
    raw4 = round(sum((d4[k].get("consensus") or 0.0)
                     for k in ("component_presence", "architectural_decision_quality")), 1)
    d4["raw_sum_before_floor"] = raw4
    cap = d4["floor_cap"]
    d4["final_dim_4_score"] = min(raw4, cap) if cap is not None else raw4

    # --- deductions from release findings (RR only; same R23 discipline as v4.6)
    deductions = []
    rr_findings = []
    for i, f in enumerate((release.get("findings") or []), 1):
        src = f.get("salesforce_source") or f.get("source_url") or ""
        if not src:
            # R23: only source-cited findings can ground a deduction or a bundle row.
            continue
        rr_findings.append({"finding_id": f.get("finding_id", f"RR-X-{i:03d}"),
                            "mechanism_name": f.get("mechanism_name") or f.get("mechanism", ""),
                            "status": f.get("status", ""),
                            "source_url": src,
                            "salesforce_source": src})
        ded = f.get("rr_deduction", 0)
        if ded:
            deductions.append({
                "id": f"RR-{i:03d}",
                "source": "Release-awareness finding (release-awareness-{a|b}.json)",
                "release_finding_ref": rr_findings[-1]["finding_id"],
                "deduction": ded,
                "triggering_passage": (f.get("triggering_passage") or f.get("evidence_note")
                                       or f'{rr_findings[-1]["mechanism_name"]} named in the SDD'),
                "salesforce_source": f.get("salesforce_source", ""),
                "rr_severity": f.get("rr_severity") or "Major",
                "rationale": f.get("consequence") or f.get("rationale")
                             or f'{rr_findings[-1]["mechanism_name"]}: {f.get("status", "")}.',
            })

    bundle = {
        "run_id": run_id,
        "blinding_label": label,
        "header": {
            "zms_version": calibration.get("zms_version"),
            "zms_frozen_at": calibration.get("zms_frozen_at"),
            "evaluator_model": run_record.get("evaluator_model_version")
                               or run_record.get("evaluator_model") or run_record.get("model_version"),
            "model_version": run_record.get("model_version"),
            "methodology_version": run_record.get("methodology_version"),
            "judge_models": dict(judge_models or {}),
        },
        "judge_runs_by_dimension": aggregate["judge_runs_by_dimension"],
        "dim_1_sub_criteria": sub_block("1"),
        "dim_2_sub_criteria": sub_block("2"),
        "dim_3_sub_criteria": d3,
        "dim_4_sub_criteria": d4,
        "dim_5_sub_criteria": sub_block("5"),
        "dim_6_sub_criteria": sub_block("6"),
        "dim_7_sub_criteria": sub_block("7"),
        "deductions": deductions,
        "per_dim_band": {d: bands.get(d, "") for d in map(str, range(1, 8))},
        "per_dim_mean": {d: round(float(means[d]), 1) for d in map(str, range(1, 8))},
        "per_dim_agreement": {d: aggregate["per_dim_agreement"].get(d)
                              for d in map(str, range(1, 8))},
        "agreement_stats": agreement_stats,
        "consensus_provenance": cons_prov,
        "dissents": aggregate.get("dissents", []),
        "per_dim_truth_source": dict(contracts.EXPECTED_TRUTH_SOURCE),
        "per_dim_key_reasoning": narrative["per_dim_key_reasoning"],
        "narrative_per_dim": narrative["narrative_per_dim"],
        "zms_calibration_citations": narrative["zms_calibration_citations"],
        "zms_calibration": {"applicable_criteria": crits},
        "content_coding": coding,
        "release_awareness_findings": rr_findings,
        "confidence_annotations_high_risk": bool(mapping.get("confidence_annotations_high_risk")),
        "blinding_attestation": contracts.BLINDING_ATTESTATION,
        "non_bias_attestation": contracts.NON_BIAS_ATTESTATION,
        "judge_independence_attestation": contracts.JUDGE_INDEPENDENCE_ATTESTATION,
    }
    return bundle


def write_bundle(path: Path, bundle: dict) -> None:
    path.write_text(json.dumps(bundle, indent=2))
