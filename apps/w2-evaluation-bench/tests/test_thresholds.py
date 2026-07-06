"""T-2 — divergence threshold boundary cases: a delta EXACTLY at 20% of
sub max / 10% of dim max is AGREEMENT (the contract is strictly-greater);
one tick above is divergence. Backend Schema section 6.3.
"""
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "engine" / "evaluate-sdd" / "scripts"))

from server import consensus  # noqa: E402
import contracts  # noqa: E402

A, B = contracts.JUDGES
CRITERIA = [{"id": "1A.x"}]
SUB_MAX = {"k": 5.0}
DIMS = ["1"]
DIM_MAX = {"1": 15}


def cards(sa, sb, da=None, db=None):
    e = {"verdict": "Present", "evidence_anchor": "the Apex trigger fires",
         "sdd_ref": "s1", "components_present": [], "components_partial": [],
         "components_absent": []}
    return {A: {"dim_scores": {"1": da if da is not None else sa},
                "sub_scores": {"1": {"k": sa}}, "verdicts": {"1A.x": dict(e)}},
            B: {"dim_scores": {"1": db if db is not None else sb},
                "sub_scores": {"1": {"k": sb}}, "verdicts": {"1A.x": dict(e)}}}


class TestSubBoundary(unittest.TestCase):
    def test_exactly_20_percent_is_agreement(self):
        # 20% of 5.0 = 1.0; scores 3.0 vs 4.0 -> delta exactly 1.0 -> AGREED
        d = consensus.diff(cards(3.0, 4.0), CRITERIA, SUB_MAX, DIMS, DIM_MAX)
        self.assertEqual(d["subs"], {})
        rec = consensus.merge(cards(3.0, 4.0), None, criteria=CRITERIA,
                              sub_max=SUB_MAX, dims=DIMS, dim_max=DIM_MAX,
                              lane="A", dim_group="1-3")
        self.assertEqual(rec["sub_scores"]["1"]["k"]["consensus"], 3.5)
        self.assertEqual(rec["sub_scores"]["1"]["k"]["provenance"], "agreed")

    def test_just_above_20_percent_diverges(self):
        d = consensus.diff(cards(3.0, 4.01), CRITERIA, SUB_MAX, DIMS, DIM_MAX)
        self.assertIn(consensus.sub_item_key("1", "k"), d["subs"])

    def test_sub_delta_frac_is_contract_sourced(self):
        self.assertEqual(contracts.SUB_DELTA_FRAC, 0.20)
        self.assertEqual(contracts.DIM_DELTA_FRAC, 0.10)


class TestDimBoundary(unittest.TestCase):
    def test_exactly_10_percent_dim_gap_not_flagged(self):
        # 10% of 15 = 1.5; dims 10.0 vs 11.5 -> exactly 1.5 -> no gap entry
        d = consensus.diff(cards(3.0, 3.0, da=10.0, db=11.5),
                           CRITERIA, SUB_MAX, DIMS, DIM_MAX)
        self.assertEqual(d["dim_gaps"], {})

    def test_just_above_10_percent_dim_gap_flagged(self):
        d = consensus.diff(cards(3.0, 3.0, da=10.0, db=11.51),
                           CRITERIA, SUB_MAX, DIMS, DIM_MAX)
        self.assertIn("1", d["dim_gaps"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
