"""P1.5 — dual-judge lift path (TR-19): consensus headline, per-judge lifts,
band = [min, max] of the three, reveal-time flip (band negates AND swaps),
dissent-flag wording in the OH §3.9 derivations (errata Q6), and the
run-level agreement roll-up (errata Q2).
"""
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "engine" / "evaluate-sdd" / "scripts"))

import contracts  # noqa: E402
import lift_calculate as LC  # noqa: E402
from tests.test_validator_v47 import make_bundle  # noqa: E402

JA, JB = contracts.JUDGES


def bundles_pair():
    """Lane A stronger than lane B, with a judge disagreement on lane A."""
    ba = make_bundle()
    # Judge A reads lane A higher than Judge B does (dim 1: 13 vs 11; cons 12)
    ba["judge_runs_by_dimension"][JA]["1"] = 13.0
    ba["judge_runs_by_dimension"][JB]["1"] = 11.0
    ba["judge_runs_by_dimension"]["consensus"]["1"] = 12.0
    ba["per_dim_mean"]["1"] = 12.0
    ba["agreement_stats"]["agreement_overall"] = 0.9
    ba["agreement_stats"]["non_na_criteria"] = 10

    bb = make_bundle()
    for d in ("1", "2", "7"):  # weaken lane B by 2 points on three dims
        for series in (JA, JB, "consensus"):
            bb["judge_runs_by_dimension"][series][d] = round(
                bb["judge_runs_by_dimension"][series][d] - 2.0, 1)
        bb["per_dim_mean"][d] = bb["judge_runs_by_dimension"]["consensus"][d]
    bb["agreement_stats"]["agreement_overall"] = 0.7
    bb["agreement_stats"]["non_na_criteria"] = 30
    return ba, bb


class TestDualJudgeLift(unittest.TestCase):
    def test_consensus_headline_and_judge_lifts(self):
        ba, bb = bundles_pair()
        ea, eb = LC.extract_from_bundle_v47(ba), LC.extract_from_bundle_v47(bb)
        lift = LC.compute_lift_metrics(ea, eb, False)
        # consensus totals: A = 80.0 (fixture) with dim1 12.0 -> fixture dim1 was 12.0
        # already, so A total unchanged at 80; B = 80 - 6 = 74 -> headline +6
        self.assertEqual(lift["headline_lift_output_a_minus_b"], 6)
        jl, band = LC.compute_judge_lifts(ea, eb, lift["headline_lift_output_a_minus_b"])
        # Judge A saw lane A at 81 (dim1 13) vs B judge total 74+? both judges of
        # lane B moved identically, so: lift_cc = 81-74 = 7; lift_gm = 79-74 = 5
        self.assertEqual(jl[JA], 7)
        self.assertEqual(jl[JB], 5)
        self.assertEqual(band, [5, 7])

    def test_flip_judge_spread_block(self):
        u = LC.judge_spread_uncertainty({JA: 7, JB: 5}, [5, 7], 0.8)
        f = LC.flip_uncertainty(u)
        self.assertEqual(f["judge_lifts"], {JA: -7, JB: -5})
        self.assertEqual((f["band_low"], f["band_high"]), (-7, -5))

    def test_flip_judge_metrics(self):
        lm = {"judge_lifts_output_a_minus_b": {JA: 7, JB: 5},
              "lift_band_output_a_minus_b": [5, 7]}
        f = LC.flip_judge_metrics(lm)
        self.assertEqual(f["judge_lifts_output_a_minus_b"], {JA: -7, JB: -5})
        self.assertEqual(f["lift_band_output_a_minus_b"], [-7, -5])

    def test_dissent_flag_wording_in_priority_review(self):
        ba, _ = bundles_pair()
        ba["dissents"] = [{"criterion_id": "5A.dependency",
                           JA: {"verdict": "Present"}, JB: {"verdict": "Absent"},
                           "conservative_resolution": {"verdict": "Absent"},
                           "why_unresolved": "irreconcilable"}]
        ea = LC.extract_from_bundle_v47(ba)
        self.assertTrue(ea["per_dim_variance_flag"]["5"])
        review = LC.derive_priority_review(ea, False, False)
        dissent_items = [e for e in review if e["issue_type"] == "Judge dissent"]
        self.assertEqual(len(dissent_items), 1)
        self.assertEqual(dissent_items[0]["source_dim"], 5)
        self.assertIn("Dissent & Reconciliation annex", dissent_items[0]["notes"])

    def test_dim7_dissent_downgrades_handoff_with_dissent_wording(self):
        ba, _ = bundles_pair()
        ba["dissents"] = [{"sub_key": "sub:7:estimable_work_units",
                           JA: 4.0, JB: 2.0, "conservative_resolution": 2.0,
                           "why_unresolved": "irreconcilable"}]
        ea = LC.extract_from_bundle_v47(ba)
        handoff = LC.derive_estimation_handoff_status(ea, False)
        self.assertEqual(handoff["status"], "Conditional")
        self.assertIn("cross-judge dissent", handoff["basis"])

    def test_run_agreement_overall_weighted(self):
        ba, bb = bundles_pair()
        ea, eb = LC.extract_from_bundle_v47(ba), LC.extract_from_bundle_v47(bb)
        # (0.9*10 + 0.7*30) / 40 = 0.75
        self.assertEqual(LC.run_agreement_overall(ea, eb), 0.75)


if __name__ == "__main__":
    unittest.main(verbosity=2)
