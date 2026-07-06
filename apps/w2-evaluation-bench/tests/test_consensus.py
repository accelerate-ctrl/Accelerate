"""T-1 — unit tests for server/consensus.py: agreement, adopt-each-side,
meet_between (bounds + strict-middle), dissent conservative rule, NA handling,
missing-criterion handling, Dim-3 netting, Dim-4 floor, determinism.

Run: python3 -m unittest tests.test_consensus  (from the app root)
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

# Synthetic dim-group "1-3"-shaped world, small enough to reason about exactly.
CRITERIA = [{"id": "1A.parse"}, {"id": "1B.persona"}, {"id": "3B.trust"}]
SUB_MAX = {"pa": 5.0, "pe": 5.0, "tr": 10.0}
DIMS = ["1", "3"]
DIM_MAX = {"1": 15, "3": 20}


def entry(verdict, anchor="the Apex trigger handles Account updates", ref="s2"):
    return {"verdict": verdict, "evidence_anchor": anchor, "sdd_ref": ref,
            "components_present": [], "components_partial": [], "components_absent": []}


def card(v1="Present", v2="Present", v3="Present", pa=4.0, pe=4.0, tr=8.0,
         anchor1="the Apex trigger handles Account updates"):
    return {"dim_scores": {"1": pa + pe, "3": tr},
            "sub_scores": {"1": {"pa": pa, "pe": pe}, "3": {"tr": tr}},
            "verdicts": {"1A.parse": entry(v1, anchor1),
                         "1B.persona": entry(v2),
                         "3B.trust": entry(v3)}}


def merge(ca, cb, rulings=None, rr=0.0, cap=None):
    return consensus.merge({A: ca, B: cb}, rulings, criteria=CRITERIA,
                           sub_max=SUB_MAX, dims=DIMS, dim_max=DIM_MAX,
                           lane="A", dim_group="1-3",
                           rr_capped_total=rr, floor_cap=cap)


class TestAgreement(unittest.TestCase):
    def test_full_agreement(self):
        rec = merge(card(), card())
        self.assertTrue(all(i["provenance"] == "agreed" for i in rec["items"].values()))
        self.assertEqual(rec["sub_scores"]["1"]["pa"]["consensus"], 4.0)
        self.assertEqual(rec["dim_scores"]["1"]["consensus"], 8.0)
        self.assertEqual(rec["stats"]["verdict_agreement_rate"], 1.0)
        self.assertEqual(rec["stats"]["score_concordance"], 1.0)
        self.assertEqual(rec["stats"]["agreement_overall"], 1.0)
        self.assertEqual(rec["stats"]["reliability_label"],
                         "strong cross-model concurrence")
        self.assertEqual(rec["dissents"], [])

    def test_agreed_subscore_is_mean_within_threshold(self):
        rec = merge(card(pa=4.0), card(pa=4.9))  # delta 0.9 <= 1.0 (20% of 5)
        self.assertEqual(rec["sub_scores"]["1"]["pa"]["consensus"], 4.5)
        self.assertEqual(rec["sub_scores"]["1"]["pa"]["provenance"], "agreed")

    def test_agreed_keeps_judge_a_anchor_and_retains_both_when_texts_differ(self):
        cb = card(anchor1="Account updates are handled by the Apex trigger layer")
        rec = merge(card(), cb)
        item = rec["items"]["1A.parse"]
        self.assertEqual(item["provenance"], "agreed")
        self.assertEqual(item["consensus"]["evidence_anchor"],
                         "the Apex trigger handles Account updates")
        self.assertIsNotNone(item["judge_entries"])


class TestDivergenceAndRulings(unittest.TestCase):
    def test_verdict_mismatch_diverges_and_adopt_each_side(self):
        ca, cb = card(v1="Present"), card(v1="Absent")
        d = consensus.diff({A: ca, B: cb}, CRITERIA, SUB_MAX, DIMS, DIM_MAX)
        self.assertIn("1A.parse", d["criteria"])
        rec = merge(ca, cb, {"1A.parse": {"ruling": "adopt_claude",
                                          "citation": "the Apex trigger handles Account updates",
                                          "rationale": "anchor resolves in section 2"}})
        self.assertEqual(rec["items"]["1A.parse"]["provenance"], "adopt_claude")
        self.assertEqual(rec["items"]["1A.parse"]["consensus"]["verdict"], "Present")
        rec2 = merge(ca, cb, {"1A.parse": {"ruling": "adopt_gemini",
                                           "citation": "x", "rationale": "y"}})
        self.assertEqual(rec2["items"]["1A.parse"]["consensus"]["verdict"], "Absent")

    def test_disjoint_anchor_same_verdict_diverges(self):
        cb = card(anchor1="completely different words about workflow rules")
        d = consensus.diff({A: card(), B: cb}, CRITERIA, SUB_MAX, DIMS, DIM_MAX)
        self.assertIn("1A.parse", d["criteria"])

    def test_meet_between_verdict_strict_middle(self):
        ca, cb = card(v1="Present"), card(v1="Absent")
        rec = merge(ca, cb, {"1A.parse": {
            "ruling": "meet_between", "citation": "a verbatim SDD passage here",
            "rationale": "half the depth components are evidenced",
            "value": {"verdict": "Partial"}}})
        self.assertEqual(rec["items"]["1A.parse"]["consensus"]["verdict"], "Partial")
        # Present vs Partial has NO strict middle -> invalid
        with self.assertRaises(ValueError):
            merge(card(v1="Present"), card(v1="Partial"),
                  {"1A.parse": {"ruling": "meet_between", "citation": "c",
                                "value": {"verdict": "Partial"}}})

    def test_missing_ruling_raises(self):
        with self.assertRaises(ValueError):
            merge(card(v1="Present"), card(v1="Absent"), {})

    def test_unknown_ruling_raises(self):
        with self.assertRaises(ValueError):
            merge(card(v1="Present"), card(v1="Absent"),
                  {"1A.parse": {"ruling": "coin_flip"}})


class TestDissentConservative(unittest.TestCase):
    def test_dissent_takes_weaker_verdict_and_its_anchor(self):
        ca = card(v1="Present")
        cb = card(v1="Partial", anchor1="only the partial workflow branch is described")
        rec = merge(ca, cb, {"1A.parse": {"ruling": "dissent",
                                          "rationale": "anchors support both readings"}})
        item = rec["items"]["1A.parse"]
        self.assertEqual(item["provenance"], "dissent")
        self.assertEqual(item["consensus"]["verdict"], "Partial")
        self.assertEqual(item["consensus"]["evidence_anchor"],
                         "only the partial workflow branch is described")
        self.assertEqual(len(rec["dissents"]), 1)
        self.assertEqual(rec["dissents"][0]["criterion_id"], "1A.parse")
        self.assertEqual(rec["stats"]["dissent_count"], 1)

    def test_na_never_wins_a_dissent(self):
        ca, cb = card(v1="NA"), card(v1="Present")
        rec = merge(ca, cb, {"1A.parse": {"ruling": "dissent", "rationale": "r"}})
        self.assertEqual(rec["items"]["1A.parse"]["consensus"]["verdict"], "Absent")

    def test_agreed_na_excluded_from_denominators(self):
        rec = merge(card(v1="NA"), card(v1="NA"))
        self.assertEqual(rec["items"]["1A.parse"]["provenance"], "agreed")
        self.assertEqual(rec["stats"]["non_na_criteria"], 2)  # only 1B, 3B count

    def test_missing_criterion_is_divergence(self):
        cb = card()
        del cb["verdicts"]["3B.trust"]
        d = consensus.diff({A: card(), B: cb}, CRITERIA, SUB_MAX, DIMS, DIM_MAX)
        self.assertIn("3B.trust", d["criteria"])
        rec = merge(card(), cb, {"3B.trust": {"ruling": "adopt_claude",
                                              "citation": "c", "rationale": "r"}})
        self.assertEqual(rec["items"]["3B.trust"]["consensus"]["verdict"], "Present")


class TestSubScores(unittest.TestCase):
    def test_sub_dissent_takes_min(self):
        ca, cb = card(tr=8.0), card(tr=4.0)  # delta 4.0 > 2.0 (20% of 10)
        ik = consensus.sub_item_key("3", "tr")
        rec = merge(ca, cb, {ik: {"ruling": "dissent", "rationale": "irreconcilable"}})
        self.assertEqual(rec["sub_scores"]["3"]["tr"]["consensus"], 4.0)
        self.assertEqual(rec["sub_scores"]["3"]["tr"]["provenance"], "dissent")
        self.assertTrue(any("sub_key" in x for x in rec["dissents"]))

    def test_sub_meet_between_bounds(self):
        ca, cb = card(tr=8.0), card(tr=4.0)
        ik = consensus.sub_item_key("3", "tr")
        rec = merge(ca, cb, {ik: {"ruling": "meet_between", "citation": "c",
                                  "value": 6.0}})
        self.assertEqual(rec["sub_scores"]["3"]["tr"]["consensus"], 6.0)
        with self.assertRaises(ValueError):
            merge(ca, cb, {ik: {"ruling": "meet_between", "citation": "c",
                                "value": 9.5}})

    def test_missing_sub_needs_ruling(self):
        cb = card()
        del cb["sub_scores"]["3"]["tr"]
        ik = consensus.sub_item_key("3", "tr")
        d = consensus.diff({A: card(), B: cb}, CRITERIA, SUB_MAX, DIMS, DIM_MAX)
        self.assertIn(ik, d["subs"])
        rec = merge(card(), cb, {ik: {"ruling": "adopt_claude", "citation": "c"}})
        self.assertEqual(rec["sub_scores"]["3"]["tr"]["consensus"], 8.0)


class TestNettingAndFloor(unittest.TestCase):
    def test_dim3_rr_netting_applied_once_to_all_three_columns(self):
        rec = merge(card(tr=8.0), card(tr=8.0), rr=-9.0)
        self.assertEqual(rec["dim_scores"]["3"][A], 0.0)   # max(0, 8-9)
        self.assertEqual(rec["dim_scores"]["3"][B], 0.0)
        self.assertEqual(rec["dim_scores"]["3"]["consensus"], 0.0)
        rec2 = merge(card(tr=8.0), card(tr=8.0), rr=-3.0)
        self.assertEqual(rec2["dim_scores"]["3"]["consensus"], 5.0)

    def test_dim4_floor_applied_to_consensus(self):
        crits = [{"id": "4A.pres"}]
        sub_max = {"cp": 9.0, "adq": 6.0}
        cards = {}
        for j in (A, B):
            cards[j] = {"dim_scores": {"4": 13.0},
                        "sub_scores": {"4": {"cp": 8.0, "adq": 5.0}},
                        "verdicts": {"4A.pres": entry("Present")}}
        rec = consensus.merge(cards, None, criteria=crits, sub_max=sub_max,
                              dims=["4"], dim_max={"4": 15}, lane="A",
                              dim_group="4-7", floor_cap=10)
        self.assertEqual(rec["dim_scores"]["4"]["consensus"], 10.0)
        self.assertEqual(rec["dim_scores"]["4"][A], 10.0)


class TestDeterminism(unittest.TestCase):
    def test_double_run_byte_equality(self):
        ca = card(v1="Present", pa=4.2)
        cb = card(v1="Absent", pa=2.9, anchor1="different anchor about workflow")
        r = {"1A.parse": {"ruling": "dissent", "rationale": "r"},
             consensus.sub_item_key("1", "pa"): {"ruling": "dissent", "rationale": "r"}}
        j1 = consensus.to_json(merge(ca, cb, r))
        j2 = consensus.to_json(merge(ca, cb, r))
        self.assertEqual(j1, j2)
        self.assertNotIn('"scored_at"', j1)  # no timestamps in the body

    def test_empty_group_edges(self):
        rec = consensus.merge(
            {A: {"dim_scores": {}, "sub_scores": {}, "verdicts": {}},
             B: {"dim_scores": {}, "sub_scores": {}, "verdicts": {}}},
            None, criteria=[], sub_max={}, dims=[], dim_max={},
            lane="A", dim_group="1-3")
        self.assertEqual(rec["items"], {})
        self.assertIsNone(rec["stats"]["agreement_overall"])


class TestLaneStatsMerge(unittest.TestCase):
    def test_merge_lane_stats_weighted(self):
        s1 = {"verdict_agreement_rate": 1.0, "verdict_agreement_rate_per_dim": {"1": 1.0},
              "score_concordance": 1.0, "score_concordance_per_dim": {"1": 1.0},
              "divergence_count": 0, "dissent_count": 0,
              "agreement_overall": 1.0, "non_na_criteria": 10}
        s2 = {"verdict_agreement_rate": 0.5, "verdict_agreement_rate_per_dim": {"4": 0.5},
              "score_concordance": 0.8, "score_concordance_per_dim": {"4": 0.8},
              "divergence_count": 5, "dissent_count": 2,
              "agreement_overall": 0.65, "non_na_criteria": 10}
        m = consensus.merge_lane_stats([s1, s2])
        self.assertEqual(m["verdict_agreement_rate"], 0.75)
        self.assertEqual(m["dissent_count"], 2)
        self.assertEqual(m["divergence_count"], 5)
        # concordance: dim1 (max 15) 1.0, dim4 (max 15) 0.8 -> 0.9
        self.assertEqual(m["score_concordance"], 0.9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
