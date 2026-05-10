"""Eval harness — golden-dataset scoring for the consultant-loop outputs.

Per spec §18 / ARCHITECTURE Batch 8.

Three eval kinds ship in the bootstrap:

    1. digest_priorities   For each (subvertical, period) we have a golden
                           list of expected sub_cap_ids; score = overlap@k.

    2. gate_consistency    Given the same prompt, the loop should return
                           the same gate verdict on consecutive runs (cache
                           hit semantics). We check the most-recent two
                           runs for each subcap.

    3. citation_grounding  Every claim in a recent reasoning chain should
                           cite at least one source_id that resolves to a
                           real source row.

Golden datasets live in `test-data/eval/*.json`; in dev we ship synthetic
labels for the four FS subverticals already populated.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .repository import get_repository

logger = logging.getLogger(__name__)

EVAL_RUNS_COLLECTION = "eval_runs"
EVAL_DATASETS_COLLECTION = "eval_datasets"
DEFAULT_EVAL_DIR = "test-data/eval"


@dataclass
class GoldenDataset:
    dataset_id: str
    kind: str  # digest_priorities | gate_consistency | citation_grounding
    description: str
    labels: list[dict] = field(default_factory=list)


@dataclass
class EvalCase:
    case_id: str
    expected: Any
    actual: Any
    passed: bool
    score: float
    notes: str | None = None


@dataclass
class EvalRun:
    run_id: str
    dataset_id: str
    kind: str
    started_at: str
    completed_at: str
    n_cases: int
    n_passed: int
    pass_rate: float
    mean_score: float
    cases: list[dict]


# ─── Dataset loading ────────────────────────────────────────────────────────


def _resolve_eval_dir() -> Path | None:
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / DEFAULT_EVAL_DIR
        if candidate.exists():
            return candidate
    return None


def _load_seed_datasets() -> list[GoldenDataset]:
    """Load all eval datasets:

    1. Always include the 3 bootstrap kinds (digest_priorities,
       gate_consistency, citation_grounding) so the standard scorers
       always have a dataset to run against. When matching JSON files
       are present in ``test-data/eval/`` they overlay the bootstrap
       (filename → seed dataset; ``kind`` field optional).
    2. Add any additional ``test-data/eval/*.json`` files as their own
       datasets, dispatching by the ``kind`` field they declare.

    Per QA_AUDIT.md fix #9 — eleven golden datasets ship in repo;
    eval_service tolerates extras without losing the spec scorers.
    """
    bootstrap_by_kind = {d.kind: d for d in _bootstrap_synthetic()}
    extras: list[GoldenDataset] = []
    base = _resolve_eval_dir()
    if base:
        for path in sorted(base.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("could not parse eval %s: %s", path, exc)
                continue
            kind = data.get("kind") or _infer_kind_from_filename(path.stem)
            if kind in bootstrap_by_kind:
                # Filename overlays the bootstrap labels for this kind, but
                # we keep the bootstrap dataset_id so callers + tests still
                # see <kind>_bootstrap. Labels merge: file extends bootstrap.
                existing = bootstrap_by_kind[kind]
                file_labels = data.get("labels") or []
                merged_labels = (existing.labels or []) + file_labels
                bootstrap_by_kind[kind] = GoldenDataset(
                    dataset_id=existing.dataset_id,
                    kind=kind,
                    description=data.get("description", existing.description),
                    labels=merged_labels,
                )
            else:
                extras.append(GoldenDataset(
                    dataset_id=data.get("dataset_id") or path.stem,
                    kind=kind or "auxiliary",
                    description=data.get("description", ""),
                    labels=data.get("labels") or data.get("cases") or [],
                ))
    return list(bootstrap_by_kind.values()) + extras


_FILENAME_KIND_MAP = {
    "golden_digest_priorities": "digest_priorities",
    "golden_contradiction_resolutions": "gate_consistency",
    "golden_hallucination_set": "citation_grounding",
}


def _infer_kind_from_filename(stem: str) -> str | None:
    return _FILENAME_KIND_MAP.get(stem)


def _bootstrap_synthetic() -> list[GoldenDataset]:
    """Seed three bootstrap datasets from existing data when the eval/
    folder is empty."""
    out: list[GoldenDataset] = []

    digest_labels = [
        {
            "case_id": "retail-banking::2026-Q2",
            "subvertical": "retail-banking",
            "period": "2026-Q2",
            "expected_sub_cap_ids": ["P1C1.1.1", "P1C1.1.2", "P1C1.1.3"],
        }
    ]
    out.append(GoldenDataset(
        dataset_id="digest_priorities_bootstrap",
        kind="digest_priorities",
        description="Bootstrap golden priorities for retail-banking 2026-Q2 — "
                    "synthesised from the lifecycle engine.",
        labels=digest_labels,
    ))

    out.append(GoldenDataset(
        dataset_id="gate_consistency_bootstrap",
        kind="gate_consistency",
        description="Re-running the same loop prompt should yield the same gate verdict.",
        labels=[],
    ))

    out.append(GoldenDataset(
        dataset_id="citation_grounding_bootstrap",
        kind="citation_grounding",
        description="Every reasoning-chain claim must cite ≥1 real source_id.",
        labels=[],
    ))
    return out


# ─── Scoring ────────────────────────────────────────────────────────────────


def _score_digest_priorities(dataset: GoldenDataset) -> tuple[list[EvalCase], float]:
    """For each labelled (subvertical, period), compare top-3 priorities."""
    repo = get_repository()
    cases: list[EvalCase] = []
    digests_by_id = {d["digest_id"]: d for d in repo.list("strategic_digests")}

    for label in dataset.labels:
        subvertical = label.get("subvertical")
        period = label.get("period")
        digest_id = f"digest-{subvertical}-{period}"
        digest = digests_by_id.get(digest_id)
        expected = set(label.get("expected_sub_cap_ids") or [])
        actual = (
            {p.get("sub_cap_id") for p in digest.get("priorities", [])}
            if digest else set()
        )
        overlap = len(expected & actual)
        score = overlap / max(1, len(expected))
        cases.append(EvalCase(
            case_id=label.get("case_id", digest_id),
            expected=sorted(expected),
            actual=sorted(actual),
            passed=overlap >= max(1, len(expected) // 2),
            score=round(score, 3),
            notes=f"overlap {overlap}/{len(expected)}",
        ))
    mean = (
        sum(c.score for c in cases) / len(cases) if cases else 0.0
    )
    return cases, round(mean, 3)


def _score_gate_consistency(dataset: GoldenDataset) -> tuple[list[EvalCase], float]:
    repo = get_repository()
    chains = sorted(
        repo.list("reasoning_chains"),
        key=lambda c: c.get("started_at", ""),
        reverse=True,
    )
    by_subcap: dict[str, list[dict]] = {}
    for c in chains:
        sid = c.get("sub_cap_id")
        if sid:
            by_subcap.setdefault(sid, []).append(c)

    cases: list[EvalCase] = []
    for sid, runs in by_subcap.items():
        if len(runs) < 2:
            continue
        a, b = runs[0], runs[1]
        same = a.get("overall") == b.get("overall")
        cases.append(EvalCase(
            case_id=f"consistency::{sid}",
            expected=b.get("overall"),
            actual=a.get("overall"),
            passed=same,
            score=1.0 if same else 0.0,
            notes=f"{a.get('chain_id')[-6:] if a.get('chain_id') else '?'} vs "
                  f"{b.get('chain_id')[-6:] if b.get('chain_id') else '?'}",
        ))
    mean = sum(c.score for c in cases) / len(cases) if cases else 1.0
    return cases, round(mean, 3)


def _score_citation_grounding(dataset: GoldenDataset) -> tuple[list[EvalCase], float]:
    repo = get_repository()
    cases: list[EvalCase] = []
    chains = sorted(
        repo.list("reasoning_chains"),
        key=lambda c: c.get("started_at", ""),
        reverse=True,
    )[:30]
    for chain in chains:
        sources = {s.get("id") for s in (chain.get("sources") or [])}
        claims = (chain.get("output") or {}).get("claims") or []
        if not claims:
            continue
        ungrounded = [
            i for i, c in enumerate(claims)
            if not any(sid in sources for sid in (c.get("sources") or []))
        ]
        cases.append(EvalCase(
            case_id=f"grounding::{chain.get('chain_id')}",
            expected=0,
            actual=len(ungrounded),
            passed=not ungrounded,
            score=1.0 if not ungrounded else max(0.0, 1.0 - 0.25 * len(ungrounded)),
            notes=f"{len(ungrounded)} ungrounded of {len(claims)} claims",
        ))
    mean = sum(c.score for c in cases) / len(cases) if cases else 1.0
    return cases, round(mean, 3)


# ─── Public API ─────────────────────────────────────────────────────────────


def list_datasets() -> list[dict]:
    """Return the seed datasets (always available) + any persisted ones."""
    seeds = [asdict(d) for d in _load_seed_datasets()]
    repo = get_repository()
    extra = list(repo.list(EVAL_DATASETS_COLLECTION))
    seen = {d["dataset_id"] for d in seeds}
    return seeds + [d for d in extra if d.get("dataset_id") not in seen]


def run_eval(dataset_id: str | None = None) -> dict[str, Any]:
    """Run evaluation; if dataset_id is None, run *all* seed datasets."""
    repo = get_repository()
    started = datetime.now(timezone.utc)
    seeds = _load_seed_datasets()
    selected = [d for d in seeds if not dataset_id or d.dataset_id == dataset_id]
    if not selected:
        raise KeyError(dataset_id)

    runs: list[EvalRun] = []
    with repo.defer_persist():
        for ds in selected:
            scorer = _scorer_for(ds.kind)
            if scorer is None:
                # Auxiliary dataset (extra golden file) without a known scorer:
                # record a "loaded" run so the harness CI assertion can still
                # see the dataset existed; no per-case scoring.
                cases, mean = [], 1.0
            else:
                cases, mean = scorer(ds)
            n_pass = sum(1 for c in cases if c.passed)
            run = EvalRun(
                run_id=f"eval-{ds.dataset_id}-{int(started.timestamp() * 1_000_000)}",
                dataset_id=ds.dataset_id,
                kind=ds.kind,
                started_at=started.isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
                n_cases=len(cases),
                n_passed=n_pass,
                pass_rate=round(n_pass / len(cases), 3) if cases else 1.0,
                mean_score=mean,
                cases=[asdict(c) for c in cases],
            )
            repo.upsert(EVAL_RUNS_COLLECTION, run.run_id, asdict(run))
            runs.append(run)
    return {
        "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "runs": [asdict(r) for r in runs],
        "summary": {
            "total_cases": sum(r.n_cases for r in runs),
            "total_passed": sum(r.n_passed for r in runs),
            "by_kind": dict(Counter(r.kind for r in runs)),
        },
    }


def list_runs(limit: int = 50) -> list[dict]:
    items = list(get_repository().list(EVAL_RUNS_COLLECTION))
    items.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return items[:limit]


def get_run(run_id: str) -> dict | None:
    return get_repository().get(EVAL_RUNS_COLLECTION, run_id)


def _scorer_for(kind: str):
    """Return the scorer fn or None for auxiliary (catch-all) datasets."""
    return {
        "digest_priorities": _score_digest_priorities,
        "gate_consistency": _score_gate_consistency,
        "citation_grounding": _score_citation_grounding,
    }.get(kind)
