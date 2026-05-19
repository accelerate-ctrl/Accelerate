"""Eval harness package — Phase 5 CI gate (Implementation Steps §10, F09).

The existing :mod:`app.services.eval_service` owns dataset loading, scoring
and run persistence. This package layers a regression-gate harness on top
that compares current mean scores to a per-dataset baseline and exits
non-zero when any dataset regresses past its tolerance.
"""

from .eval_harness import (
    BASELINE_COLLECTION,
    DatasetBaseline,
    HarnessResult,
    list_baselines,
    run_harness,
    set_baseline,
    set_baseline_from_run,
)

__all__ = [
    "BASELINE_COLLECTION",
    "DatasetBaseline",
    "HarnessResult",
    "list_baselines",
    "run_harness",
    "set_baseline",
    "set_baseline_from_run",
]
