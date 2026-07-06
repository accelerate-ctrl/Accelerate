#!/usr/bin/env python3
"""
accuracy_gate.py — LIVE verdict self-consistency check for the Present/Partial/Absent verdict step.

This SUPERSEDES the development-time 20-fixture harness. Unlike that harness
(which ran outside the deployed skill and only as a manual step), this check:

  1. ships INSIDE the skill and is invoked DURING the pipeline (batch 2.5),
  2. reads a validation set that scales toward all 99 criteria and accepts
     HUMAN-VALIDATED / EXPERT-PANEL labels (stronger than construction-rule),
  3. ENFORCES a measured self-consistency threshold — blocking the run when
     authority conditions are met, advisory when the labeled data is too thin,
  4. emits a calibration block that the diagnostic report surfaces, so every
     report states the verdict-step self-consistency basis (or its absence).

What it measures (and what it does NOT): the rest of the pipeline validates
STRUCTURE and CONSISTENCY (R1-R25, variance, bands). This check measures how
often the model's verdicts AGREE with the deterministic construction-rule labels
on a small validation set. That is self-consistency against known-answer cases —
NOT external accuracy over all 99 criteria — and the report must always present
it that way. It is advisory unless the labeled set is strong and broad enough to
enforce. (The internal field is still named `accuracy` for the agreement rate;
the user-facing label is self-consistency.)

WORKFLOW (in-pipeline, batch 2.5 — after ZMS load, before scoring):
  1. The orchestrator scores each validation excerpt against its criterion using
     the SAME verdict procedure it will use for the real SDD (the SA playbook),
     producing {case_id: verdict}.
  2. This module compares predictions to the labeled verdicts, computes the
     agreement rate and per-class recall, applies the gate policy, and writes
     accuracy-gate.json.
  3. If the check BLOCKS, the orchestrator must HALT and surface the failure — the
     verdict step is not self-consistent enough to trust this run.

Standalone self-test (no model; CI guard on the gate math itself):
  python3 accuracy_gate.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CLASSES = ("Present", "Partial", "Absent")
DATA = Path(__file__).resolve().parent.parent / "data" / "accuracy-validation-set.json"


def load_validation_set(path: Path = DATA) -> dict:
    vs = json.loads(Path(path).read_text())
    cases = vs.get("cases", [])
    seen = set()
    for c in cases:
        assert c["id"] not in seen, f"duplicate case id {c['id']}"
        seen.add(c["id"])
        assert c["gold_verdict"] in CLASSES, f"{c['id']}: bad gold {c['gold_verdict']!r}"
        assert c.get("excerpt", "").strip(), f"{c['id']}: empty excerpt"
        assert c.get("criterion_id", "").strip(), f"{c['id']}: empty criterion_id"
        assert c.get("label_source") in (
            "expert_panel", "human_validated", "sa_exemplar", "construction_rule"), \
            f"{c['id']}: bad label_source {c.get('label_source')!r}"
    return vs


def score_predictions(predictions: dict, vs: dict) -> dict:
    """predictions: {case_id: verdict}. Returns the full accuracy report."""
    cases = vs.get("cases", [])
    gold = {c["id"]: c["gold_verdict"] for c in cases}
    confusion = {a: {b: 0 for b in CLASSES} for a in CLASSES}
    scored = 0
    correct = 0
    missing = []
    for cid, g in gold.items():
        if cid not in predictions:
            missing.append(cid)
            continue
        p = predictions[cid]
        if p not in CLASSES:
            missing.append(cid)
            continue
        confusion[g][p] += 1
        scored += 1
        if p == g:
            correct += 1

    def _prf(cls):
        tp = confusion[cls][cls]
        fp = sum(confusion[o][cls] for o in CLASSES if o != cls)
        fn = sum(confusion[cls][o] for o in CLASSES if o != cls)
        prec = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * prec * rec / (prec + rec)) if (prec and rec) else None
        return {"precision": _r(prec), "recall": _r(rec), "f1": _r(f1),
                "support": tp + fn}

    per_class = {c: _prf(c) for c in CLASSES}
    # label-quality breakdown — authority scales with human/expert fraction
    by_source = {}
    for c in cases:
        by_source[c["label_source"]] = by_source.get(c["label_source"], 0) + 1
    human_like = by_source.get("human_validated", 0) + by_source.get("expert_panel", 0)
    return {
        "scored": scored,
        "missing_predictions": missing,
        "accuracy": _r(correct / scored) if scored else None,
        "per_class": per_class,
        "confusion_matrix": confusion,
        "label_source_counts": by_source,
        "human_validated_fraction": _r(human_like / len(cases)) if cases else 0.0,
        "cases_total": len(cases),
        "criteria_covered": len(set(c["criterion_id"] for c in cases)),
    }


def apply_gate(report: dict, vs: dict) -> dict:
    """Apply the gate policy. Returns a verdict block with pass/block/advisory."""
    pol = vs.get("gate_policy", {})
    min_acc = pol.get("min_overall_accuracy", 0.85)
    min_rec = pol.get("min_per_class_recall", 0.75)
    min_cases = pol.get("min_cases_for_enforcement", 30)
    min_human_frac = pol.get("min_human_validated_fraction_for_full_authority", 0.5)

    acc = report.get("accuracy")
    scored = report.get("scored", 0)
    human_frac = report.get("human_validated_fraction", 0.0)

    reasons = []
    # Can we ENFORCE (block) at all? Requires enough cases AND enough human labels.
    enforceable = (scored >= min_cases) and (human_frac >= min_human_frac)

    accuracy_ok = (acc is not None) and (acc >= min_acc)
    recall_ok = True
    for cls, m in report.get("per_class", {}).items():
        r = m.get("recall")
        if m.get("support", 0) > 0 and r is not None and r < min_rec:
            recall_ok = False
            reasons.append(f"{cls} recall {r} < {min_rec}")
    if acc is not None and acc < min_acc:
        reasons.append(f"overall accuracy {acc} < {min_acc}")

    if not enforceable:
        status = "advisory"
        blocking = False
        why = (f"Validation set too thin to enforce (scored={scored} < {min_cases} "
               f"or human/expert fraction {human_frac} < {min_human_frac}). Accuracy "
               f"is reported for transparency but does NOT block. Add human-validated "
               f"labels across more criteria to enable enforcement.")
    elif accuracy_ok and recall_ok:
        status = "pass"
        blocking = False
        why = f"Verdict accuracy {acc} meets the >= {min_acc} threshold with per-class recall satisfied."
    else:
        status = "block"
        blocking = True
        why = "Verdict step failed the self-consistency check: " + "; ".join(reasons) + \
              ". The model's verdicts do not agree with the deterministic labels often enough to trust this run."

    return {
        "status": status,            # pass | advisory | block
        "blocking": blocking,
        "enforceable": enforceable,
        "thresholds": {"min_overall_accuracy": min_acc, "min_per_class_recall": min_rec,
                       "min_cases_for_enforcement": min_cases,
                       "min_human_validated_fraction": min_human_frac},
        "measured_accuracy": acc,
        "human_validated_fraction": human_frac,
        "cases_scored": scored,
        "criteria_covered": report.get("criteria_covered"),
        "explanation": why,
        "report_caveat": _report_caveat(status, report, min_acc),
    }


def _report_caveat(status, report, min_acc):
    acc = report.get("accuracy")
    cov = report.get("criteria_covered")
    if status == "advisory":
        return (f"CALIBRATION COVERAGE LIMITED: verdict self-consistency was measured on "
                f"{report.get('scored',0)} validation case(s) across {cov} of 99 "
                f"criteria, mostly construction-rule labels. Measured self-consistency "
                f"{acc if acc is not None else 'n/a'} (agreement with the deterministic "
                f"construction-rule labels, not external accuracy over all criteria). This "
                f"is advisory only; the scores in this report rest on the model's unvalidated "
                f"judgment for criteria outside the validation set. Treat findings as a "
                f"senior-SA opinion to verify, not a calibrated measurement.")
    if status == "block":
        return (f"VERDICT SELF-CONSISTENCY CHECK FAILED (measured {acc} < {min_acc} on the "
                f"construction-rule validation set). This report should NOT be relied upon; "
                f"the verdict step did not agree with the deterministic labels often enough "
                f"to trust this run.")
    return (f"Verdict self-consistency {acc} met the >= {min_acc} bar on "
            f"{report.get('scored',0)} construction-rule cases across {cov} of 99 criteria "
            f"(agreement with deterministic labels, not external accuracy).")


def _r(x):
    return round(x, 3) if isinstance(x, (int, float)) else x


def _selftest() -> int:
    """CI guard on the gate MATH (no model). Oracles must behave correctly."""
    vs = load_validation_set()
    cases = vs.get("cases", [])
    ok = True

    # perfect oracle -> accuracy 1.0
    perfect = {c["id"]: c["gold_verdict"] for c in cases}
    rep = score_predictions(perfect, vs)
    if rep["accuracy"] != 1.0:
        print(f"  FAIL: perfect oracle accuracy {rep['accuracy']} != 1.0"); ok = False
    else:
        print("  PASS: perfect oracle scores 1.0")

    # trivial all-Absent oracle must NOT score 1.0 (anti-gaming)
    trivial = {c["id"]: "Absent" for c in cases}
    rep2 = score_predictions(trivial, vs)
    if rep2["accuracy"] == 1.0:
        print("  FAIL: trivial all-Absent oracle scored 1.0 (validation set degenerate)"); ok = False
    else:
        print(f"  PASS: trivial all-Absent oracle scores {rep2['accuracy']} (< 1.0)")

    # gate policy: with the seed (construction-rule only) set, gate must be advisory
    g = apply_gate(score_predictions(perfect, vs), vs)
    if g["status"] != "advisory" or g["blocking"]:
        print(f"  FAIL: thin construction-rule set should be advisory, got {g['status']}"); ok = False
    else:
        print("  PASS: thin/construction-rule set is advisory (not blocking) — honest authority scaling")

    # synthetic enforceable+failing set must BLOCK
    fake_vs = {
        "cases": [{"id": f"H{i}", "criterion_id": f"{i}A.x", "gold_verdict": "Present",
                   "excerpt": "x", "label_source": "human_validated"} for i in range(40)],
        "gate_policy": vs["gate_policy"],
    }
    bad_preds = {f"H{i}": ("Present" if i < 10 else "Absent") for i in range(40)}  # 25% acc
    gb = apply_gate(score_predictions(bad_preds, fake_vs), fake_vs)
    if gb["status"] != "block" or not gb["blocking"]:
        print(f"  FAIL: enforceable low-accuracy set should BLOCK, got {gb['status']}"); ok = False
    else:
        print(f"  PASS: enforceable low-accuracy set BLOCKS (acc {gb['measured_accuracy']})")

    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Live verdict self-consistency check (verdict step).")
    ap.add_argument("--predictions", type=Path,
                    help="JSON {case_id: verdict} from the orchestrator scoring the validation excerpts.")
    ap.add_argument("--validation-set", type=Path, default=DATA)
    ap.add_argument("--output", type=Path, help="Write accuracy-gate.json here.")
    ap.add_argument("--selftest", action="store_true", help="Run the no-model gate-math oracles.")
    args = ap.parse_args()

    if args.selftest:
        rc = _selftest()
        print("ACCURACY-GATE SELFTEST:", "PASS" if rc == 0 else "FAIL")
        return rc

    vs = load_validation_set(args.validation_set)
    if not args.predictions:
        # No predictions supplied: emit the coverage/authority status so the
        # orchestrator knows whether the gate will enforce, and report stays honest.
        rep = {"scored": 0, "accuracy": None, "per_class": {},
               "confusion_matrix": {}, "cases_total": len(vs.get("cases", [])),
               "criteria_covered": len(set(c["criterion_id"] for c in vs.get("cases", []))),
               "human_validated_fraction": _r(
                   sum(1 for c in vs.get("cases", []) if c["label_source"] in
                       ("human_validated", "expert_panel")) / max(1, len(vs.get("cases", []))))}
        gate = apply_gate(rep, vs)
        out = {"status": "no_predictions", "gate": gate, "report": rep,
               "note": "Run the validation excerpts through the verdict step and pass --predictions to measure accuracy."}
    else:
        preds = json.loads(args.predictions.read_text())
        # v4.6 (shape guard): the contract is a FLAT {case_id: verdict} map. A
        # wrapped or mis-keyed file previously scored 0 cases silently and the
        # gate still reported "advisory" — making a malformed hand-off
        # indistinguishable from a thin validation set. Fail loud instead.
        if not isinstance(preds, dict):
            print(json.dumps({"status": "error",
                              "reason_code": "PREDICTIONS_SHAPE_MISMATCH",
                              "detail": "predictions file must be a flat JSON object "
                                        "{case_id: verdict}, e.g. {\"GF-01\": \"Present\"}."},
                             indent=2), file=sys.stderr)
            return 2
        case_ids = {c["id"] for c in vs.get("cases", [])}
        if preds and not (set(preds.keys()) & case_ids):
            print(json.dumps({"status": "error",
                              "reason_code": "PREDICTIONS_SHAPE_MISMATCH",
                              "detail": "predictions file is non-empty but no key matches a "
                                        "validation-set case id — expected a flat "
                                        "{case_id: verdict} map (keys like 'GF-01'). "
                                        "Did you wrap it in {\"predictions\": {...}} or key "
                                        "by criterion_id?"},
                             indent=2), file=sys.stderr)
            return 2
        rep = score_predictions(preds, vs)
        gate = apply_gate(rep, vs)
        out = {"status": gate["status"], "gate": gate, "report": rep}

    text = json.dumps(out, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(text)
    print(text)
    # exit non-zero on a blocking gate so the pipeline can HALT on it
    return 2 if out.get("gate", {}).get("blocking") else 0


if __name__ == "__main__":
    sys.exit(main())
