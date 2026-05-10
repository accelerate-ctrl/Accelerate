"""Entity resolver precision/recall metrics.

Per QA_AUDIT.md fix #16. Loads ``test-data/eval/golden_entity_resolution.json``
and reports precision (negative pairs not collapsed) + recall (positive
pairs collapsed correctly). Targets: precision ≥ 0.95, recall ≥ 0.85.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .entity_resolver import resolve

_GOLDEN_PATH_REL = "test-data/eval/golden_entity_resolution.json"


def _find_golden() -> Path | None:
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / _GOLDEN_PATH_REL
        if candidate.exists():
            return candidate
    return None


def evaluate() -> dict[str, Any]:
    """Run the resolver against the golden labels; return P/R + per-case detail."""
    path = _find_golden()
    if not path:
        return {"error": "golden_entity_resolution.json not found"}
    data = json.loads(path.read_text(encoding="utf-8"))
    pos = data.get("positive_pairs") or []
    neg = data.get("negative_pairs") or []

    tp = fp = tn = fn = 0
    pos_results: list[dict] = []
    neg_results: list[dict] = []
    for pair in pos:
        a = resolve(pair["a"], kind="client")
        b = resolve(pair["b"], kind="client")
        same = a.canonical == b.canonical
        pos_results.append({**pair, "actual_a": a.canonical, "actual_b": b.canonical,
                            "collapsed": same})
        if same:
            tp += 1
        else:
            fn += 1
    for pair in neg:
        a = resolve(pair["a"], kind="client")
        b = resolve(pair["b"], kind="client")
        same = a.canonical == b.canonical
        neg_results.append({**pair, "actual_a": a.canonical, "actual_b": b.canonical,
                            "collapsed": same})
        if same:
            fp += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "n_positive": len(pos), "n_negative": len(neg),
        "pos_results": pos_results,
        "neg_results": neg_results,
    }
