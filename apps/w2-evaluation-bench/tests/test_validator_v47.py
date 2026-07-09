"""T-4 — v4.7 validator rules: the re-pointed R3/R4/R5, the R14/R25
extensions over reconcile output, and the new R26/R27/R28 — each with a
passing case and every failure mode. Also asserts the frozen v4.6 path is
untouched by the switch (R2 still enforced there).

Run: python3 -m unittest tests.test_validator_v47
"""
import copy
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "engine" / "evaluate-sdd" / "scripts"))

import contracts  # noqa: E402
import score_sheet_populate as SSP  # noqa: E402

JA, JB = contracts.JUDGES
ANCHOR = "the Apex trigger updates the Account records nightly per section 2"
CID_BY_DIM = {"1": "1A.parse", "2": "2A.trace", "3": "3A.module",
              "4": "4A.presence", "5": "5A.dependency", "6": "6A.scope",
              "7": "7A.units"}


def make_bundle() -> dict:
    """A minimal fully VALID v4.7 bundle (agreed everywhere, no deductions)."""
    b = {"run_id": "W2-TEST", "blinding_label": "Output A",
         "header": {"zms_version": "4.6", "zms_frozen_at": "2026-01-01",
                    "evaluator_model": "panel:claude-code+gemini",
                    "model_version": "panel:claude-code+gemini",
                    "methodology_version": "4.7",
                    "judge_models": {JA: "claude-test", JB: "gemini-2.5-flash"}},
         "deductions": [], "dissents": [],
         "per_dim_truth_source": dict(contracts.EXPECTED_TRUTH_SOURCE),
         "blinding_attestation": contracts.BLINDING_ATTESTATION,
         "non_bias_attestation": contracts.NON_BIAS_ATTESTATION,
         "judge_independence_attestation": contracts.JUDGE_INDEPENDENCE_ATTESTATION,
         "consensus_provenance": {}, "content_coding": {},
         "zms_calibration": {"applicable_criteria": [
             {"id": cid} for cid in CID_BY_DIM.values()]},
         "release_awareness_findings": [],
         "per_dim_key_reasoning": {}, "narrative_per_dim": {},
         "zms_calibration_citations": {},
         "judge_runs_by_dimension": {JA: {}, JB: {}, "consensus": {}},
         "per_dim_mean": {}, "per_dim_band": {}, "per_dim_agreement": {}}

    for d, subs in SSP.SUBCRIT.items():
        block = {}
        for sid, key in subs:
            if sid == "3E":
                block[key] = None  # single-cloud engagement
                continue
            mx = SSP.SUB_MAX_LOOKUP[key] if hasattr(SSP, "SUB_MAX_LOOKUP") else None
            val = round(0.8 * _sub_max(key), 1)
            block[key] = {JA: val, JB: val, "consensus": val,
                          "provenance": "agreed", "max": _sub_max(key),
                          "reasoning": ("Consensus sub-criterion result for "
                                        f"{key}: both judges coded the cited Apex "
                                        "trigger evidence Present per section 2.")}
        b["dim_%s_sub_criteria" % d] = block
        total = round(sum(v["consensus"] for v in block.values() if v), 1)
        if d == "4":
            block["floor_cap"] = None
            block["raw_sum_before_floor"] = total
            block["final_dim_4_score"] = total
        for series in (JA, JB, "consensus"):
            b["judge_runs_by_dimension"][series][d] = total
        b["per_dim_mean"][d] = total
        b["per_dim_band"][d] = contracts.band_for_pct(
            100.0 * total / contracts.dim_max(int(d)))
        b["per_dim_agreement"][d] = 1.0

        cid = CID_BY_DIM[d]
        b["consensus_provenance"][cid] = "agreed"
        b["content_coding"][subs[0][1]] = {
            "zms_components": [{"zms_criterion_id": cid,
                                "source_label": "Zennify SDD standard",
                                "severity": "", "verdict": "Present",
                                "evidence_anchor": ANCHOR, "sdd_ref": "section 2",
                                "components_present": [], "components_partial": [],
                                "components_absent": [], "provenance": "agreed"}],
            "candidate_present": [], "candidate_partial": [],
            "candidate_absent": [], "coverage": 1.0}
        brd = " Requirements grounding: SF-1 and BRD section 1." if d in ("1", "2", "6") else ""
        b["per_dim_key_reasoning"][d] = (
            f"Consensus mean {total}: the decisive comparison was {cid}, where the "
            f"coded Apex trigger evidence met the calibration bar.{brd}")
        b["narrative_per_dim"][d] = (
            f"Dimension {d} landed at {total} on the strength of the coded evidence.")
        b["zms_calibration_citations"][d] = [{
            "zms_criterion_id": cid, "source_label": "Zennify SDD standard",
            "brd_ref": "SF-1", "sdd_ref": "section 2", "verdict": "Present",
            "evidence_anchor": ANCHOR,
            "observation": "Against the calibration bar this criterion coded Present "
                           "with the trigger mechanism named."}]

    b["agreement_stats"] = {
        "verdict_agreement_rate": 1.0,
        "verdict_agreement_rate_per_dim": {d: 1.0 for d in CID_BY_DIM},
        "score_concordance": 1.0,
        "score_concordance_per_dim": {d: 1.0 for d in CID_BY_DIM},
        "divergence_count": 0, "dissent_count": 0,
        "agreement_overall": 1.0, "non_na_criteria": 7,
        "reliability_label": "strong cross-model concurrence"}
    return b


def _sub_max(key: str) -> float:
    m = {"requirement_parsing_depth": 5, "stakeholder_persona_recognition": 5,
         "constraint_assumption_extraction": 5, "functional_requirement_traceability": 5,
         "nfr_coverage": 5, "gap_risk_identification": 5, "cloud_module_selection": 5,
         "trusted_design": 5, "easy_design": 5, "adaptable_design": 5,
         "multi_cloud_architecture": 5, "component_presence": 9,
         "architectural_decision_quality": 6, "dependency_id_classification": 4,
         "assumption_documentation": 3, "integration_failure_modes": 3,
         "in_out_delineation": 4, "phasing_prioritisation": 3,
         "scope_creep_resistance": 3, "estimable_work_units": 5,
         "complexity_effort_indicators": 5, "delivery_readiness_signals": 5}
    return float(m[key])


def validate(b):
    return SSP.validate_bundle_v47(b, "Output A")


def errors_for(b, rule):
    ok, errors = validate(b)
    return [e for e in errors if e.startswith(rule)]


class TestBaselineValid(unittest.TestCase):
    def test_fixture_is_fully_valid(self):
        ok, errors = validate(make_bundle())
        self.assertTrue(ok, f"expected valid fixture, got: {errors}")


class TestR3R4R5(unittest.TestCase):
    def test_r3_consensus_recompute_failure(self):
        b = make_bundle()
        b["per_dim_mean"]["1"] = b["per_dim_mean"]["1"] + 2.0
        self.assertTrue(errors_for(b, "R3"))

    def test_r3_dim3_net_of_deductions(self):
        b = make_bundle()
        b["deductions"] = [{"id": "RR-001", "deduction": -3,
                            "triggering_passage": "Workflow Rules named in section 4",
                            "salesforce_source": "https://help.salesforce.com/x",
                            "release_finding_ref": "RR-A-001"}]
        b["release_awareness_findings"] = [{"finding_id": "RR-A-001",
                                            "source_url": "https://help.salesforce.com/x"}]
        # per_dim_mean["3"] no longer nets the -3 -> R3 must fire
        self.assertTrue(errors_for(b, "R3"))
        # netting it restores validity
        b["per_dim_mean"]["3"] = round(b["per_dim_mean"]["3"] - 3.0, 1)
        b["judge_runs_by_dimension"]["consensus"]["3"] = b["per_dim_mean"]["3"]
        # judges' own dim-3 totals must also sit net for the envelope check
        b["judge_runs_by_dimension"][JA]["3"] = b["per_dim_mean"]["3"]
        b["judge_runs_by_dimension"][JB]["3"] = b["per_dim_mean"]["3"]
        b["per_dim_band"]["3"] = contracts.band_for_pct(
            100.0 * b["per_dim_mean"]["3"] / 20)
        ok, errors = validate(b)
        self.assertTrue(ok, errors)

    def test_r4_missing_judge_series_value(self):
        b = make_bundle()
        del b["judge_runs_by_dimension"][JB]["5"]
        self.assertTrue(errors_for(b, "R4") or errors_for(b, "R28"))

    def test_r4_consensus_escapes_envelope(self):
        b = make_bundle()
        b["judge_runs_by_dimension"][JA]["6"] = 4.0
        b["judge_runs_by_dimension"][JB]["6"] = 5.0
        # consensus stays at fixture value 8.0 -> outside [4, 5]
        self.assertTrue(errors_for(b, "R4"))

    def test_r5_wrong_per_dim_agreement(self):
        b = make_bundle()
        b["per_dim_agreement"]["2"] = 0.5
        self.assertTrue(errors_for(b, "R5"))

    def test_r5_incoherent_overall(self):
        b = make_bundle()
        b["agreement_stats"]["agreement_overall"] = 0.4
        self.assertTrue(errors_for(b, "R5"))

    def test_r5_missing_stats_object(self):
        b = make_bundle()
        b["agreement_stats"] = {}
        self.assertTrue(errors_for(b, "R5"))


class TestR14R25Extensions(unittest.TestCase):
    def _diverge(self, b, prov="adopt_claude"):
        cid = CID_BY_DIM["1"]
        comp = b["content_coding"]["requirement_parsing_depth"]["zms_components"][0]
        comp["provenance"] = prov
        comp["judge_entries"] = {
            JA: {"verdict": "Present", "evidence_anchor": ANCHOR, "sdd_ref": "s2"},
            JB: {"verdict": "Partial",
                 "evidence_anchor": "only the Flow branch is described in section 3",
                 "sdd_ref": "s3"}}
        comp["ruling_citation"] = ANCHOR
        comp["ruling_rationale"] = "the cited trigger passage satisfies the depth bar"
        b["consensus_provenance"][cid] = prov
        return b, cid, comp

    def test_extended_fields_pass_when_grounded(self):
        b, _, _ = self._diverge(make_bundle())
        ok, errors = validate(b)
        self.assertTrue(ok, errors)

    def test_r14_leak_in_ruling_rationale(self):
        b, _, comp = self._diverge(make_bundle())
        comp["ruling_rationale"] = "the ZenAgent lane is clearly stronger here"
        self.assertTrue(errors_for(b, "R14"))

    def test_r14_leak_in_dissent_record(self):
        b = make_bundle()
        b["dissents"] = [{"criterion_id": CID_BY_DIM["7"],
                          JA: {"verdict": "Present", "evidence_anchor": ANCHOR},
                          JB: {"verdict": "Partial", "evidence_anchor": ANCHOR},
                          "conservative_resolution": {"verdict": "Partial"},
                          "why_unresolved": "the OTS lane reads differently"}]
        self.assertTrue(errors_for(b, "R14"))

    def test_r25_ungrounded_ruling_citation(self):
        b, _, comp = self._diverge(make_bundle())
        comp["ruling_citation"] = "see capability detail above"
        self.assertTrue(errors_for(b, "R25"))

    def test_r25_judge_anchor_verdict_restatement(self):
        b, _, comp = self._diverge(make_bundle(), prov="adopt_gemini")
        comp["judge_entries"][JB]["evidence_anchor"] = "coded Partial against the bar"
        self.assertTrue(errors_for(b, "R25"))


class TestR26(unittest.TestCase):
    def test_missing_provenance_entry(self):
        b = make_bundle()
        del b["consensus_provenance"][CID_BY_DIM["4"]]
        self.assertTrue(errors_for(b, "R26"))

    def test_unknown_provenance_value(self):
        b = make_bundle()
        b["consensus_provenance"][CID_BY_DIM["4"]] = "coin_flip"
        self.assertTrue(errors_for(b, "R26"))

    def test_non_agreed_without_judge_entries(self):
        b = make_bundle()
        cid = CID_BY_DIM["5"]
        b["consensus_provenance"][cid] = "adopt_claude"
        comp = b["content_coding"]["dependency_id_classification"]["zms_components"][0]
        comp["provenance"] = "adopt_claude"
        comp["ruling_citation"] = ANCHOR
        # judge_entries deliberately absent
        self.assertTrue(errors_for(b, "R26"))

    def test_ruling_without_citation(self):
        b = make_bundle()
        cid = CID_BY_DIM["5"]
        b["consensus_provenance"][cid] = "adopt_gemini"
        comp = b["content_coding"]["dependency_id_classification"]["zms_components"][0]
        comp["provenance"] = "adopt_gemini"
        comp["judge_entries"] = {JA: {"verdict": "Present", "evidence_anchor": ANCHOR},
                                 JB: {"verdict": "Partial", "evidence_anchor": ANCHOR}}
        self.assertTrue(errors_for(b, "R26"))


class TestR27(unittest.TestCase):
    def _dissent(self, b, resolution="Partial"):
        cid = CID_BY_DIM["6"]
        b["consensus_provenance"][cid] = "dissent"
        comp = b["content_coding"]["in_out_delineation"]["zms_components"][0]
        comp["provenance"] = "dissent"
        comp["judge_entries"] = {
            JA: {"verdict": "Present", "evidence_anchor": ANCHOR},
            JB: {"verdict": "Partial",
                 "evidence_anchor": "only the Flow branch is described in section 3"}}
        b["dissents"] = [{"criterion_id": cid,
                          JA: {"verdict": "Present", "evidence_anchor": ANCHOR},
                          JB: {"verdict": "Partial", "evidence_anchor": ANCHOR},
                          "conservative_resolution": {"verdict": resolution},
                          "why_unresolved": "both anchors are genuine and conflicting"}]
        return b, cid

    def test_valid_dissent_passes(self):
        b, _ = self._dissent(make_bundle())
        ok, errors = validate(b)
        self.assertTrue(ok, errors)

    def test_wrong_conservative_resolution(self):
        b, _ = self._dissent(make_bundle(), resolution="Present")
        self.assertTrue(errors_for(b, "R27"))

    def test_provenance_dissent_without_record(self):
        b, cid = self._dissent(make_bundle())
        b["dissents"] = []
        self.assertTrue(errors_for(b, "R27"))

    def test_duplicate_dissent_record(self):
        b, cid = self._dissent(make_bundle())
        b["dissents"] = b["dissents"] * 2
        self.assertTrue(errors_for(b, "R27"))

    def test_sub_dissent_min_rule(self):
        b = make_bundle()
        b["dissents"] = [{"sub_key": "sub:7:estimable_work_units",
                          JA: 4.0, JB: 2.0, "conservative_resolution": 4.0,
                          "why_unresolved": "score readings irreconcilable"}]
        self.assertTrue(errors_for(b, "R27"))


class TestR28(unittest.TestCase):
    def test_missing_attestation(self):
        b = make_bundle()
        del b["judge_independence_attestation"]
        self.assertTrue(errors_for(b, "R28"))
        self.assertTrue(errors_for(b, "R17"))  # also in the required set

    def test_tampered_attestation(self):
        b = make_bundle()
        b["judge_independence_attestation"] = "I promise the judges were independent."
        self.assertTrue(errors_for(b, "R28"))

    def test_wrong_judge_series(self):
        b = make_bundle()
        b["judge_runs_by_dimension"]["gpt"] = b["judge_runs_by_dimension"].pop(JB)
        self.assertTrue(errors_for(b, "R28"))


class TestLegacyPathFrozen(unittest.TestCase):
    def test_v46_validator_still_enforces_r2(self):
        ok, errors = SSP.validate_bundle(make_bundle(), "Output A")
        self.assertFalse(ok)
        self.assertTrue(any(e.startswith("R2") for e in errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
