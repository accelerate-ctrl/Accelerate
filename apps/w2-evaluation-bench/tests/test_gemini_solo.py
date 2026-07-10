"""Single-AI Gemini mode (runner --engine gemini): slot routing, model-tier
assignment, and the no-Claude guarantee. No network — pure routing logic."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "runner"))

import w2_runner  # noqa: E402


class GeminiSoloRouting(unittest.TestCase):
    def test_pass_packets_route_to_their_slots(self):
        pa = {"kind": "pass", "meta": {"judge": "claude-code"}}
        pb = {"kind": "pass", "meta": {"judge": "gemini"}}
        self.assertEqual(w2_runner.route_judge(pa, "gemini"), "claude-code")
        self.assertEqual(w2_runner.route_judge(pb, "gemini"), "gemini")

    def test_unrouted_kinds_go_to_slot_a(self):
        for kind in ("reconcile", "narrative", "exec_narrative",
                     "components", "features", "evidence"):
            self.assertEqual(
                w2_runner.route_judge({"kind": kind, "meta": {}}, "gemini"),
                "claude-code", kind)

    def test_model_tiers_differ_per_slot(self):
        ma = w2_runner.gemini_model_for("claude-code")
        mb = w2_runner.gemini_model_for("gemini")
        self.assertNotEqual(ma, mb)
        self.assertIn("gemini", ma)
        self.assertIn("gemini", mb)
        # slot A gets the deeper tier by default
        self.assertIn("pro", ma)

    def test_no_claude_dependency_in_gemini_mode(self):
        # main() must not require the claude executable for engine=gemini:
        # the preflight branch imports gemini_judge only. Assert statically.
        src = (ROOT / "runner" / "w2_runner.py").read_text()
        block = src.split('if args.engine == "gemini":')[1]
        block = block.split('elif args.engine in ("claude-code", "panel")')[0]
        self.assertNotIn("billing_guard.preflight", block)
        self.assertNotIn("claude_exe =", block)


if __name__ == "__main__":
    unittest.main()
