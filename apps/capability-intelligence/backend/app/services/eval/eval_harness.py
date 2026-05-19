"""F09 — Phase 5 eval harness with CI regression gate.

The harness runs every golden dataset that ships in ``test-data/eval/`` plus
the synthetic bootstrap kinds, compares each dataset's ``mean_score`` to a
persisted baseline, and reports per-dataset verdicts.

Usage from CI::

    python -m app.services.eval.eval_harness run --strict

``--strict`` returns exit code 1 on the first regression so the gate
blocks merges. ``set-baseline`` snapshots the current scores so a
subsequent run can be compared.

Baselines live in the ``eval_baselines`` repository collection — that
keeps them with the rest of the eval data (runs, datasets) and lets the
harness work whether the repository is in-memory (tests) or Firestore
(production).

The harness is intentionally a thin wrapper around
:mod:`app.services.eval_service` so the legacy API + tests keep working
unchanged.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .. import eval_service
from ..repository import get_repository

logger = logging.getLogger(__name__)

BASELINE_COLLECTION = "eval_baselines"
DEFAULT_TOLERANCE = float(os.getenv("EVAL_BASELINE_TOLERANCE", "0.05"))
DEFAULT_MIN_PASS_RATE = float(os.getenv("EVAL_MIN_PASS_RATE", "0.0"))


@dataclass
class DatasetBaseline:
    dataset_id: str
    mean_score: float
    pass_rate: float
    tolerance: float = DEFAULT_TOLERANCE
    min_pass_rate: float = DEFAULT_MIN_PASS_RATE
    captured_at: str = ""
    schema_version_: str = "eval-baseline-v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DatasetVerdict:
    dataset_id: str
    kind: str
    mean_score: float
    pass_rate: float
    baseline_mean: float | None
    baseline_pass_rate: float | None
    tolerance: float
    regressed: bool
    reason: str | None = None
    n_cases: int = 0
    n_passed: int = 0


@dataclass
class HarnessResult:
    started_at: str
    completed_at: str
    n_datasets: int
    n_regressed: int
    overall_mean: float
    verdicts: list[DatasetVerdict] = field(default_factory=list)
    runs: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "n_datasets": self.n_datasets,
            "n_regressed": self.n_regressed,
            "overall_mean": self.overall_mean,
            "verdicts": [asdict(v) for v in self.verdicts],
            "runs": self.runs,
        }

    @property
    def passed(self) -> bool:
        return self.n_regressed == 0


# ─── Baseline persistence ────────────────────────────────────────────────────


def list_baselines() -> list[dict[str, Any]]:
    return list(get_repository().list(BASELINE_COLLECTION))


def _get_baseline(dataset_id: str) -> DatasetBaseline | None:
    rec = get_repository().get(BASELINE_COLLECTION, dataset_id)
    if not rec:
        return None
    return DatasetBaseline(
        dataset_id=rec["dataset_id"],
        mean_score=float(rec.get("mean_score", 0.0)),
        pass_rate=float(rec.get("pass_rate", 0.0)),
        tolerance=float(rec.get("tolerance", DEFAULT_TOLERANCE)),
        min_pass_rate=float(rec.get("min_pass_rate", DEFAULT_MIN_PASS_RATE)),
        captured_at=rec.get("captured_at", ""),
    )


def set_baseline(
    dataset_id: str,
    *,
    mean_score: float,
    pass_rate: float,
    tolerance: float | None = None,
    min_pass_rate: float | None = None,
) -> DatasetBaseline:
    baseline = DatasetBaseline(
        dataset_id=dataset_id,
        mean_score=round(float(mean_score), 4),
        pass_rate=round(float(pass_rate), 4),
        tolerance=float(tolerance) if tolerance is not None else DEFAULT_TOLERANCE,
        min_pass_rate=(
            float(min_pass_rate)
            if min_pass_rate is not None
            else DEFAULT_MIN_PASS_RATE
        ),
        captured_at=datetime.now(timezone.utc).isoformat(),
    )
    get_repository().upsert(
        BASELINE_COLLECTION, dataset_id, baseline.to_dict()
    )
    return baseline


def set_baseline_from_run(
    run: dict[str, Any],
    *,
    tolerance: float | None = None,
    min_pass_rate: float | None = None,
) -> DatasetBaseline:
    return set_baseline(
        run["dataset_id"],
        mean_score=run.get("mean_score", 0.0),
        pass_rate=run.get("pass_rate", 0.0),
        tolerance=tolerance,
        min_pass_rate=min_pass_rate,
    )


# ─── Harness ────────────────────────────────────────────────────────────────


def _verdict_for(
    run: dict[str, Any], baseline: DatasetBaseline | None
) -> DatasetVerdict:
    mean = float(run.get("mean_score", 0.0))
    pass_rate = float(run.get("pass_rate", 0.0))
    if baseline is None:
        # No baseline yet — never blocks CI, but surface as a warning row so
        # the operator notices a dataset is unanchored.
        return DatasetVerdict(
            dataset_id=run["dataset_id"],
            kind=run.get("kind", ""),
            mean_score=mean,
            pass_rate=pass_rate,
            baseline_mean=None,
            baseline_pass_rate=None,
            tolerance=DEFAULT_TOLERANCE,
            regressed=False,
            reason="no baseline; first-run snapshot — set via set-baseline",
            n_cases=int(run.get("n_cases", 0)),
            n_passed=int(run.get("n_passed", 0)),
        )

    floor = baseline.mean_score - baseline.tolerance
    regressed = mean < floor
    reason = None
    if regressed:
        reason = (
            f"mean_score {mean:.3f} < floor {floor:.3f} "
            f"(baseline {baseline.mean_score:.3f} − tol {baseline.tolerance:.3f})"
        )
    elif pass_rate < baseline.min_pass_rate:
        regressed = True
        reason = (
            f"pass_rate {pass_rate:.3f} < min {baseline.min_pass_rate:.3f}"
        )
    return DatasetVerdict(
        dataset_id=run["dataset_id"],
        kind=run.get("kind", ""),
        mean_score=mean,
        pass_rate=pass_rate,
        baseline_mean=baseline.mean_score,
        baseline_pass_rate=baseline.pass_rate,
        tolerance=baseline.tolerance,
        regressed=regressed,
        reason=reason,
        n_cases=int(run.get("n_cases", 0)),
        n_passed=int(run.get("n_passed", 0)),
    )


def run_harness(
    dataset_ids: Iterable[str] | None = None,
) -> HarnessResult:
    """Run the harness over all (or a subset of) golden datasets.

    Returns a :class:`HarnessResult` whose ``passed`` property is False if
    any dataset regressed past its baseline tolerance.
    """
    started = datetime.now(timezone.utc)
    target_ids = set(dataset_ids) if dataset_ids else None

    summary = eval_service.run_eval(dataset_id=None)
    runs = summary.get("runs", [])
    if target_ids is not None:
        runs = [r for r in runs if r.get("dataset_id") in target_ids]

    verdicts: list[DatasetVerdict] = []
    for run in runs:
        baseline = _get_baseline(run["dataset_id"])
        verdicts.append(_verdict_for(run, baseline))

    n_regressed = sum(1 for v in verdicts if v.regressed)
    overall_mean = (
        round(sum(v.mean_score for v in verdicts) / len(verdicts), 4)
        if verdicts
        else 1.0
    )
    return HarnessResult(
        started_at=started.isoformat(),
        completed_at=datetime.now(timezone.utc).isoformat(),
        n_datasets=len(verdicts),
        n_regressed=n_regressed,
        overall_mean=overall_mean,
        verdicts=verdicts,
        runs=runs,
    )


# ─── CLI ────────────────────────────────────────────────────────────────────


def _print_summary(result: HarnessResult) -> None:
    print(
        f"eval harness — {result.n_datasets} datasets, "
        f"{result.n_regressed} regressed, "
        f"overall mean {result.overall_mean:.3f}"
    )
    for v in result.verdicts:
        marker = "REGRESS" if v.regressed else "ok"
        base = (
            f"{v.baseline_mean:.3f}"
            if v.baseline_mean is not None
            else "—"
        )
        print(
            f"  [{marker:7}] {v.dataset_id:<40} kind={v.kind:<22} "
            f"mean={v.mean_score:.3f} (baseline {base})"
            + (f" — {v.reason}" if v.reason else "")
        )


def _cmd_run(args: argparse.Namespace) -> int:
    result = run_harness(args.dataset_ids or None)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        _print_summary(result)
    if args.strict and not result.passed:
        return 1
    return 0


def _cmd_set_baseline(args: argparse.Namespace) -> int:
    summary = eval_service.run_eval(dataset_id=None)
    runs = summary.get("runs", [])
    targets = set(args.dataset_ids or []) or {r["dataset_id"] for r in runs}
    captured = []
    for run in runs:
        if run["dataset_id"] not in targets:
            continue
        b = set_baseline_from_run(
            run, tolerance=args.tolerance, min_pass_rate=args.min_pass_rate
        )
        captured.append(b.to_dict())
    if args.json:
        print(json.dumps(captured, indent=2, default=str))
    else:
        print(f"captured baseline for {len(captured)} datasets")
        for b in captured:
            print(
                f"  {b['dataset_id']:<40} mean={b['mean_score']:.3f} "
                f"pass_rate={b['pass_rate']:.3f} tol={b['tolerance']:.3f}"
            )
    return 0


def _cmd_list_baselines(args: argparse.Namespace) -> int:
    rows = list_baselines()
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
    else:
        for b in rows:
            print(
                f"  {b['dataset_id']:<40} mean={b['mean_score']:.3f} "
                f"tol={b['tolerance']:.3f} captured_at={b.get('captured_at', '?')}"
            )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eval-harness")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run all golden datasets")
    run.add_argument("--dataset-ids", nargs="*", dest="dataset_ids")
    run.add_argument("--strict", action="store_true",
                     help="exit non-zero on regression")
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=_cmd_run)

    snap = sub.add_parser("set-baseline", help="snapshot current scores")
    snap.add_argument("--dataset-ids", nargs="*", dest="dataset_ids")
    snap.add_argument("--tolerance", type=float, default=None)
    snap.add_argument("--min-pass-rate", type=float, default=None)
    snap.add_argument("--json", action="store_true")
    snap.set_defaults(func=_cmd_set_baseline)

    listb = sub.add_parser("list-baselines", help="show stored baselines")
    listb.add_argument("--json", action="store_true")
    listb.set_defaults(func=_cmd_list_baselines)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
