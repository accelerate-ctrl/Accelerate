#!/usr/bin/env python3
"""Screener calibration CLI (learning loop 1).

    python3 scripts/calibrate.py           # fit from ledger, gate on gold, apply
    python3 scripts/calibrate.py --dry     # fit + gate report only, no write
    python3 scripts/calibrate.py --status  # current params + ledger size

Fits the autonomous screener's thresholds from the consensus-history ledger
(AI-judged runs only) and applies them ONLY if the gold-corpus verdict
benchmark stays >= 95% under the candidate params."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "engine" / "evaluate-sdd" / "scripts"))

from server import learning  # noqa: E402
from server import auto_judge  # noqa: E402


def main(argv):
    import os
    include_mock = os.environ.get("W2_LEARN_FROM_MOCK") == "1"
    if "--status" in argv:
        print("params :", json.dumps(auto_judge.get_params()))
        print("ledger :", len(learning.load_rows(include_mock=True)), "rows",
              f"({len(learning.load_rows())} eligible for fitting)")
        print("file   :", learning.PARAMS,
              "(exists)" if learning.PARAMS.exists() else "(defaults active)")
        return 0
    rows = learning.load_rows(include_mock=include_mock)
    fitres = learning.fit(rows)
    print(f"ledger rows used: {fitres['n']}")
    print(f"history accuracy: baseline {fitres['baseline_accuracy']} -> "
          f"fitted {fitres['accuracy']} with {json.dumps(fitres['params'])}")
    if "--dry" in argv:
        ok, gold = learning.gold_gate(fitres["params"])
        print(f"gold gate: {'PASS' if ok else 'REJECT'} ({gold:.1%})")
        return 0
    out = learning.apply(fitres)
    if out["applied"]:
        print(f"APPLIED: gold accuracy {out['gold_accuracy']:.1%} — "
              f"params written to {learning.PARAMS}")
        return 0
    print(f"REJECTED: {out.get('rejected')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
