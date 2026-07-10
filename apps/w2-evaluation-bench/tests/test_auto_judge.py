"""Autonomous judge (server/auto_judge.py): verdict integrity, verbatim
anchors, provenance honesty, determinism. Verdict ACCURACY vs the
hand-labeled gold is enforced separately in test_nlp_accuracy (the
benchmark's `verdicts` component, >=95%)."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine" / "evaluate-sdd" / "scripts"))
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

import auto_judge  # noqa: E402
import gold_corpus as G  # noqa: E402


def _pass_packet(judge: str) -> dict:
    crits = [c for c, _ in G.GOLD_EVIDENCE][:3]
    for c in crits:
        c.setdefault("parent_sub_criterion", "1A")
        c.setdefault("dimension", 1)
    prompt = (f"=== SDD (Output A) ===\n{G.GOLD_SDD}\n"
              f"=== ZMS CALIBRATION SLICE (dims 1-3) ===\n"
              + json.dumps({"criteria": crits}))
    return {"packet_id": f"pass:Output A:1-3:1:{judge}", "kind": "pass",
            "label": "Output A", "prompt": prompt,
            "meta": {"dim_group": "1-3", "pass_n": 1, "judge": judge}}


class ScoringPass(unittest.TestCase):
    def test_shape_verdicts_and_verbatim_anchors(self):
        out = auto_judge.execute(_pass_packet("claude-code"))
        self.assertEqual(set(out), {"dim_scores", "sub_scores", "verdicts"})
        self.assertEqual(len(out["verdicts"]), 3)
        for cid, rec in out["verdicts"].items():
            self.assertIn(rec["verdict"], ("Present", "Partial", "Absent"))
            if rec["verdict"] != "Absent":
                self.assertIn(rec["evidence_anchor"], G.GOLD_SDD,
                              f"{cid} anchor must be a verbatim SDD slice")

    def test_deterministic(self):
        a = auto_judge.execute(_pass_packet("claude-code"))
        b = auto_judge.execute(_pass_packet("claude-code"))
        self.assertEqual(a, b)

    def test_judge_slots_run_distinct_philosophies(self):
        va = auto_judge.execute(_pass_packet("claude-code"))["verdicts"]
        vb = auto_judge.execute(_pass_packet("gemini"))["verdicts"]
        order = {"Present": 3, "Partial": 2, "Absent": 1}
        for cid in va:
            # B is coverage-primary: never LOOSER than A, at most one step
            self.assertLessEqual(order[vb[cid]["verdict"]],
                                 order[va[cid]["verdict"]])
            self.assertLessEqual(order[va[cid]["verdict"]]
                                 - order[vb[cid]["verdict"]], 1)


class Provenance(unittest.TestCase):
    def test_usage_reports_screener_engine(self):
        u = auto_judge.usage_for(_pass_packet("gemini"))
        self.assertEqual(u["engine"], "auto-screener")
        self.assertEqual(u["judge"], "gemini")   # TR-8: slot addressed
        self.assertEqual(u["total_cost_usd"], 0.0)
        self.assertEqual(u["input_tokens"], 0)

    def test_exec_narrative_discloses_autonomy(self):
        pkt = {"packet_id": "exec", "kind": "exec_narrative", "label": "Output A",
               "prompt": "=== REVEALED RUN DIGEST ===\n"
                         + json.dumps({"lift_metrics": {}, "cross_model_concurrence":
                                       {"agreement_overall": 0.9}})}
        out = auto_judge.execute(pkt)
        text = out["exec_narrative"]["confidence_caveats"]
        self.assertIn("AUTONOMOUS SCREENING MODE", text)
        self.assertIn("no AI model judged", text)


if __name__ == "__main__":
    unittest.main()
