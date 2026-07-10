"""Learning loop 1: ledger recording, threshold fitting, and the gold-corpus
gate that makes self-training safe."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "engine" / "evaluate-sdd" / "scripts"))

from server import auto_judge, learning  # noqa: E402


def _row(n, np_, npa, nab, top, final):
    return {"n_comps": n, "n_present": np_, "n_partial": npa, "n_absent": nab,
            "top_matched": top, "final": final, "engines": ["claude-code"]}


class FitAndPredict(unittest.TestCase):
    def test_predict_mirrors_screener_rule(self):
        # 2 comps present, none absent, strong candidate -> Present at defaults
        self.assertEqual(learning._predict(_row(2, 2, 0, 0, 2, ""), 2, 3), "Present")
        # weak candidate blocks Present, evidence remains -> Partial
        self.assertEqual(learning._predict(_row(2, 2, 0, 0, 1, ""), 2, 3), "Partial")
        self.assertEqual(learning._predict(_row(2, 0, 0, 2, 0, ""), 2, 3), "Absent")

    def test_fit_moves_toward_history(self):
        # history where top_matched==1 items were finally ruled Present:
        rows = [_row(2, 2, 0, 0, 1, "Present") for _ in range(20)]
        rows += [_row(1, 0, 0, 1, 0, "Absent") for _ in range(5)]
        res = learning.fit(rows)
        self.assertEqual(res["params"]["min_matched_terms"], 1)
        self.assertGreater(res["accuracy"], res["baseline_accuracy"])

    def test_fit_empty_ledger_keeps_defaults(self):
        res = learning.fit([])
        self.assertEqual(res["params"], learning.DEFAULTS)
        self.assertEqual(res["n"], 0)


class GoldGate(unittest.TestCase):
    def test_defaults_pass_and_strict_params_rejected(self):
        ok, gold = learning.gold_gate(dict(learning.DEFAULTS))
        self.assertTrue(ok, f"defaults must hold the floor, got {gold}")
        ok3, gold3 = learning.gold_gate({"min_matched_terms": 3,
                                         "present_deficit_div": 3})
        self.assertFalse(ok3, f"mmt=3 should break gold Presents, got {gold3}")

    def test_apply_rejects_below_floor_without_writing(self):
        tmp = Path(tempfile.mkdtemp())
        old = (learning.LEARN_DIR, learning.LEDGER, learning.PARAMS)
        learning.LEARN_DIR, learning.LEDGER, learning.PARAMS = \
            tmp, tmp / "ledger.jsonl", tmp / "params.json"
        try:
            bad = {"params": {"min_matched_terms": 3, "present_deficit_div": 3},
                   "accuracy": 1.0, "baseline_accuracy": 0.5, "n": 9}
            out = learning.apply(bad)
            self.assertFalse(out["applied"])
            self.assertFalse((tmp / "params.json").exists())
            good = {"params": dict(learning.DEFAULTS),
                    "accuracy": 1.0, "baseline_accuracy": 1.0, "n": 9}
            out2 = learning.apply(good)
            self.assertTrue(out2["applied"])
            saved = json.loads((tmp / "params.json").read_text())
            self.assertEqual(saved["min_matched_terms"], 2)
            self.assertGreaterEqual(saved["gold_accuracy"], 0.95)
        finally:
            learning.LEARN_DIR, learning.LEDGER, learning.PARAMS = old
            auto_judge.invalidate_params()

    def test_candidate_env_params_change_screener(self):
        import os
        os.environ["W2_SCREENER_PARAMS"] = json.dumps(
            {"min_matched_terms": 3, "present_deficit_div": 3})
        auto_judge.invalidate_params()
        try:
            self.assertEqual(auto_judge.get_params()["min_matched_terms"], 3)
        finally:
            os.environ.pop("W2_SCREENER_PARAMS", None)
            auto_judge.invalidate_params()


class LedgerFilter(unittest.TestCase):
    def test_mock_rows_excluded_from_fitting(self):
        tmp = Path(tempfile.mkdtemp())
        old = (learning.LEARN_DIR, learning.LEDGER, learning.PARAMS)
        learning.LEARN_DIR, learning.LEDGER, learning.PARAMS = \
            tmp, tmp / "ledger.jsonl", tmp / "params.json"
        try:
            with learning.LEDGER.open("w") as fh:
                fh.write(json.dumps({**_row(2, 2, 0, 0, 2, "Present"),
                                     "engines": ["mock"]}) + "\n")
                fh.write(json.dumps(_row(2, 2, 0, 0, 2, "Present")) + "\n")
            self.assertEqual(len(learning.load_rows()), 1)
            self.assertEqual(len(learning.load_rows(include_mock=True)), 2)
        finally:
            learning.LEARN_DIR, learning.LEDGER, learning.PARAMS = old


if __name__ == "__main__":
    unittest.main()


class Loop2To4(unittest.TestCase):
    def test_slot_warning_flags_swapped_uploads(self):
        sys.path.insert(0, str(ROOT / "tests"))
        import gold_corpus as G
        import nlp
        self.assertIsNotNone(nlp.slot_warning("brd", G.GOLD_SDD))
        self.assertIsNotNone(nlp.slot_warning("sdd", G.GOLD_BRD))
        self.assertIsNone(nlp.slot_warning("brd", G.GOLD_BRD))
        self.assertIsNone(nlp.slot_warning("sdd", G.GOLD_SDD))

    def test_feedback_weights_beta_mean(self):
        tmp = Path(tempfile.mkdtemp())
        old = (learning.LEARN_DIR, learning.FEEDBACK)
        learning.LEARN_DIR, learning.FEEDBACK = tmp, tmp / "feedback.jsonl"
        try:
            for useful in (True, True, False):
                learning.record_feedback("r1", "op", "F-101", useful, "d1:gap")
            w = learning.feedback_weights()
            self.assertAlmostEqual(w["d1:gap"], (2 + 1) / (3 + 2))
        finally:
            learning.LEARN_DIR, learning.FEEDBACK = old
