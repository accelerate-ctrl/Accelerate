"""Accuracy gate for the pre-intelligence layer: every component must hold
>=95% on the hand-labeled gold corpus (tests/gold_corpus.py), measured by the
same grader the CLI benchmark uses (scripts/nlp_benchmark.py). A change that
drops any component below the bar fails the suite — the 95% floor is a
contract, not a report."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import nlp_benchmark  # noqa: E402


class NlpAccuracy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = nlp_benchmark.run_benchmark()

    def test_every_component_meets_threshold(self):
        for name, c in sorted(self.res["components"].items()):
            with self.subTest(component=name):
                self.assertGreaterEqual(
                    c["accuracy"], nlp_benchmark.THRESHOLD,
                    f"{name} at {c['accuracy']:.1%}; failures: {c['failures']}")

    def test_overall_meets_threshold(self):
        self.assertGreaterEqual(self.res["overall"]["accuracy"],
                                nlp_benchmark.THRESHOLD)
        self.assertTrue(self.res["ok"])

    def test_corpus_is_adversarial_not_trivial(self):
        # The gate only means something while the corpus keeps its negative
        # (must-NOT-flag) instances alongside the positives.
        checks = [i["check"] for i in self.res["instances"]]
        self.assertTrue(any(c.startswith("rejects") for c in checks))
        self.assertTrue(any(c.startswith("plain-English") for c in checks))
        self.assertTrue(any(c.startswith("clean:") for c in checks))
        self.assertGreaterEqual(self.res["overall"]["total"], 80)

    def test_benchmark_deterministic(self):
        again = nlp_benchmark.run_benchmark()
        self.assertEqual(self.res, again)


if __name__ == "__main__":
    unittest.main()
