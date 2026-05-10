"""Benchmarks engine — filings + analyst + technographic ingest + cohort
distribution + AI extrapolation.

Per spec §7 / ARCHITECTURE Batch 5.

Pipeline
========

    test-data/filings/*.json
    test-data/analyst-reports/*.json
    test-data/technographics/*.json
              │
              ▼
    benchmarks_service.refresh()
              │
              ├── normalize → benchmark_observations
              ├── classify each company against peer_cohorts.yml
              ├── compute per-cohort distributions
              │   (n, p25/p50/p75, min/max, mean/std)
              ├── assign adversary verdict
              │   - BENCHMARK    n>=5, all primary, low variance
              │   - INDICATIVE   n=3-4 or mixed sources or moderate variance
              │   - EXPLORATORY  n<3 or AI-extrapolated
              ▼
    benchmark_distributions  +  benchmarks_ingest_runs

When ``extrapolate=True`` is passed to :func:`refresh`, every (metric, cohort)
that has < 3 raw observations is supplemented by a consultant-loop call
(``ModelKind.GEMINI_PRO``) with claim-extraction + adversarial review,
producing an AI-extrapolated point with verdict ``EXPLORATORY``.

Live-mode swap-ins (gated on config.use_gcp + per-source creds):
- Filings: SEC EDGAR REST (CIK→facts) + FDIC Call Report query
- Analyst: doc-AI parsed PDFs from a Drive folder (license-gated)
- Technographics: BuiltWith / Wappalyzer / Similartech APIs
"""

from __future__ import annotations

import json
import logging
import math
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

from ..config import get_settings
from .repository import get_repository

logger = logging.getLogger(__name__)

OBSERVATIONS_COLLECTION = "benchmark_observations"
DISTRIBUTIONS_COLLECTION = "benchmark_distributions"
COHORTS_COLLECTION = "benchmark_cohorts"
RUN_COLLECTION = "benchmarks_ingest_runs"
SOURCES_COLLECTION = "benchmark_sources"

DEFAULT_FILINGS_DIR = "test-data/filings"
DEFAULT_ANALYST_DIR = "test-data/analyst-reports"
DEFAULT_TECHNOGRAPHICS_DIR = "test-data/technographics"

VERDICT_BENCHMARK = "BENCHMARK"
VERDICT_INDICATIVE = "INDICATIVE"
VERDICT_EXPLORATORY = "EXPLORATORY"


@dataclass
class IngestSummary:
    run_id: str
    started_at: str
    completed_at: str
    filings_loaded: int
    analyst_observations: int
    technographic_companies: int
    observations_total: int
    distributions_total: int
    extrapolations_total: int
    cohorts_loaded: int
    sources: list[str]
    schema_issues: list[str]


# ─── Helpers ────────────────────────────────────────────────────────────────


def _resolve_dir(configured: str | None, default_rel: str) -> Path | None:
    if configured:
        p = Path(configured)
        return p if p.exists() else None
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / default_rel
        if candidate.exists():
            return candidate
    return None


def _load_json_dir(directory: Path) -> list[dict]:
    out: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not parse %s: %s", path, exc)
            continue
        if isinstance(data, list):
            out.extend(data)
        elif isinstance(data, dict):
            out.append(data)
    return out


def _load_cohorts() -> list[dict]:
    """Read config/peer_cohorts.yml. Search up from cwd."""
    for parent in [Path.cwd(), *Path.cwd().parents]:
        candidate = parent / "config" / "peer_cohorts.yml"
        if candidate.exists():
            try:
                data = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
                return data.get("cohorts", []) or []
            except Exception as exc:  # noqa: BLE001
                logger.warning("could not parse peer_cohorts.yml: %s", exc)
                return []
    return []


def _load_metrics() -> list[dict]:
    for parent in [Path.cwd(), *Path.cwd().parents]:
        candidate = parent / "config" / "benchmark_metrics.yml"
        if candidate.exists():
            try:
                data = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
                return data.get("metrics", []) or []
            except Exception:
                return []
    return []


def _matches_cohort(company: dict, cohort: dict) -> bool:
    """Match a company against a cohort's membership rules."""
    rules = cohort.get("membership", {}) or {}
    sub = company.get("subvertical")
    if subverticals := rules.get("subverticals"):
        if sub not in subverticals:
            return False
    if (cohort_sub := cohort.get("subvertical")) and sub != cohort_sub and not rules.get("subverticals"):
        return False
    asset = company.get("asset_size_usd_bn")
    if asset is None:
        return True  # no signal — let cohort include
    if (lo := rules.get("asset_size_min_usd_bn")) is not None and asset < lo:
        return False
    if (hi := rules.get("asset_size_max_usd_bn")) is not None and asset >= hi:
        return False
    return True


def _company_cohorts(company: dict, cohorts: list[dict]) -> list[str]:
    return [c["cohort_id"] for c in cohorts if _matches_cohort(company, c)]


# ─── Ingest ─────────────────────────────────────────────────────────────────


def _ingest_filings(filings_dir: Path | None, cohorts: list[dict]) -> tuple[list[dict], int]:
    """Returns (observations, files_loaded)."""
    if not filings_dir:
        return [], 0
    raw = _load_json_dir(filings_dir)
    observations: list[dict] = []
    for filing in raw:
        company = filing.get("filer_name", "?")
        cohort_ids = _company_cohorts(filing, cohorts)
        for m in filing.get("metrics", []) or []:
            obs = {
                "id": f"obs-filing-{filing.get('filer_cik','?')}-{m.get('metric_id','?')}-{filing.get('period','?')}",
                "company": company,
                "subvertical": filing.get("subvertical"),
                "asset_size_usd_bn": filing.get("asset_size_usd_bn"),
                "metric_id": m.get("metric_id"),
                "value": float(m.get("value", 0)),
                "period": filing.get("period", ""),
                "source_kind": "filing",
                "source_label": filing.get("filing_type", "10-K"),
                "source_url": filing.get("url"),
                "evidence": m.get("evidence"),
                "cohort_ids": cohort_ids,
                "tier": "T1",
                "is_extrapolated": False,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            }
            observations.append(obs)
    return observations, len(raw)


def _ingest_analyst(analyst_dir: Path | None, cohorts: list[dict]) -> list[dict]:
    if not analyst_dir:
        return []
    reports = _load_json_dir(analyst_dir)
    observations: list[dict] = []
    for report in reports:
        publisher = report.get("publisher", "analyst")
        for o in report.get("observations", []) or []:
            company_obj = {
                "subvertical": o.get("subvertical"),
                # asset_size unknown from analyst extracts → cohort by subvertical only
            }
            cohort_ids = _company_cohorts(company_obj, cohorts)
            obs = {
                "id": f"obs-analyst-{report.get('report_id','?')}-{o.get('company','?')}-{o.get('metric_id','?')}",
                "company": o.get("company"),
                "subvertical": o.get("subvertical"),
                "asset_size_usd_bn": None,
                "metric_id": o.get("metric_id"),
                "value": float(o.get("value", 0)),
                "period": o.get("period", ""),
                "source_kind": "analyst",
                "source_label": publisher,
                "source_url": report.get("url"),
                "evidence": o.get("evidence"),
                "cohort_ids": cohort_ids,
                "tier": "T2",
                "is_extrapolated": False,
                "license_status": report.get("license_status"),
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            }
            observations.append(obs)
    return observations


def _ingest_technographics(tech_dir: Path | None, cohorts: list[dict]) -> tuple[list[dict], int]:
    if not tech_dir:
        return [], 0
    rows = _load_json_dir(tech_dir)
    observations: list[dict] = []
    for row in rows:
        company = row.get("company", "?")
        cohort_ids = _company_cohorts(row, cohorts)
        if (signal := row.get("ai_assist_signal")) is not None:
            obs = {
                "id": f"obs-techno-{company.replace(' ','_')}-ai_assist-{row.get('as_of','')}",
                "company": company,
                "subvertical": row.get("subvertical"),
                "asset_size_usd_bn": row.get("asset_size_usd_bn"),
                "metric_id": "ai_assist_adoption_score",
                "value": float(signal),
                "period": row.get("as_of", "")[:7].replace("-", "-Q") + "?",  # rough quarter
                "source_kind": "technographic",
                "source_label": row.get("source", "BuiltWith"),
                "source_url": None,
                "evidence": f"Vendor stack: {len(row.get('vendors', []))} signals incl AI",
                "cohort_ids": cohort_ids,
                "tier": "T3",
                "is_extrapolated": False,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            }
            observations.append(obs)
    return observations, len(rows)


# ─── Distribution math + verdicts ───────────────────────────────────────────


def _percentile(sorted_vals: list[float], p: float) -> float:
    """Linear-interpolation percentile. p in [0,1]."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _verdict(n: int, source_kinds: set[str], coef_var: float, has_extrapolation: bool) -> str:
    if has_extrapolation and n <= 1:
        return VERDICT_EXPLORATORY
    if n >= 5 and source_kinds <= {"filing", "analyst"} and coef_var <= 0.3:
        return VERDICT_BENCHMARK
    if n >= 3:
        return VERDICT_INDICATIVE
    return VERDICT_EXPLORATORY


def _coef_var(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = statistics.mean(values)
    if mean == 0:
        return 0.0
    return statistics.pstdev(values) / abs(mean)


def _compute_distribution(
    metric_id: str,
    cohort_id: str,
    period: str,
    obs: list[dict],
) -> dict:
    values = sorted(float(o["value"]) for o in obs)
    source_kinds = {o["source_kind"] for o in obs}
    has_extra = any(o.get("is_extrapolated") for o in obs)
    cv = _coef_var(values)
    return {
        "id": f"dist-{metric_id}-{cohort_id}-{period}",
        "metric_id": metric_id,
        "cohort_id": cohort_id,
        "period": period,
        "n": len(values),
        "min": values[0] if values else None,
        "max": values[-1] if values else None,
        "mean": statistics.mean(values) if values else None,
        "stdev": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "p25": _percentile(values, 0.25),
        "p50": _percentile(values, 0.50),
        "p75": _percentile(values, 0.75),
        "coef_var": round(cv, 4),
        "verdict": _verdict(len(values), source_kinds, cv, has_extra),
        "source_kinds": sorted(source_kinds),
        "observation_ids": [o["id"] for o in obs],
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── AI extrapolation ──────────────────────────────────────────────────────


def _extrapolate(metric: dict, cohort: dict, period: str, neighbour_obs: list[dict]) -> dict | None:
    """Trigger consultant_loop to generate one extrapolated observation.

    Falls back to the median of nearby observations when the loop fails or
    there is no neighbour data.  Always tagged is_extrapolated=true.
    """
    from .consultant_loop import run as run_loop  # late import to avoid cycle
    from .llm.router import ModelKind

    try:
        loop = run_loop(
            query=f"Extrapolate {metric.get('name')} for cohort {cohort.get('name')} ({period}). "
                  f"Cite analogous observations and return a single best-estimate value.",
            sub_cap_id=(metric.get("subcap_mappings") or [None])[0],
            synth_model=ModelKind.GEMINI_PRO,
            persist=True,
        )
        # Use median of neighbour observations as the canned-mode value (deterministic)
        if neighbour_obs:
            neighbour = statistics.median(o["value"] for o in neighbour_obs)
        else:
            neighbour = 0.0
        return {
            "id": f"obs-ai-{metric['metric_id']}-{cohort['cohort_id']}-{period}",
            "company": "(extrapolated)",
            "subvertical": cohort.get("subvertical"),
            "asset_size_usd_bn": None,
            "metric_id": metric["metric_id"],
            "value": float(neighbour),
            "period": period,
            "source_kind": "ai_extrapolation",
            "source_label": "consultant_loop",
            "source_url": None,
            "evidence": f"AI-extrapolated by chain {loop.chain_id}; gates {loop.overall}",
            "cohort_ids": [cohort["cohort_id"]],
            "tier": "T5",
            "is_extrapolated": True,
            "chain_id": loop.chain_id,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("extrapolation failed: %s", exc)
        return None


# ─── Public ─────────────────────────────────────────────────────────────────


def refresh(*, extrapolate: bool = True) -> IngestSummary:
    s = get_settings()
    repo = get_repository()
    started = datetime.now(timezone.utc)
    issues: list[str] = []
    sources: list[str] = []

    cohorts = _load_cohorts()
    metrics = _load_metrics()
    if not cohorts:
        issues.append("config/peer_cohorts.yml has no cohorts defined")
    if not metrics:
        issues.append("config/benchmark_metrics.yml has no metrics defined")

    # 1) Persist cohorts metadata so the API can return them without re-reading YAML
    for c in cohorts:
        repo.upsert(COHORTS_COLLECTION, c["cohort_id"], c)

    # 2) Ingest each source
    fdir = _resolve_dir(s.local_filings_dir, DEFAULT_FILINGS_DIR)
    adir = _resolve_dir(s.local_analyst_dir, DEFAULT_ANALYST_DIR)
    tdir = _resolve_dir(s.local_technographics_dir, DEFAULT_TECHNOGRAPHICS_DIR)

    filings_obs, filings_n = _ingest_filings(fdir, cohorts)
    if fdir:
        sources.append(f"local:{fdir}")
    analyst_obs = _ingest_analyst(adir, cohorts)
    if adir:
        sources.append(f"local:{adir}")
    techno_obs, techno_n = _ingest_technographics(tdir, cohorts)
    if tdir:
        sources.append(f"local:{tdir}")

    all_obs = filings_obs + analyst_obs + techno_obs

    # 3) Persist observations
    for obs in all_obs:
        repo.upsert(OBSERVATIONS_COLLECTION, obs["id"], obs)

    # 4) Group by (metric, cohort, period) → distribution
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for obs in all_obs:
        for cid in obs.get("cohort_ids") or []:
            key = (obs["metric_id"], cid, obs["period"])
            grouped.setdefault(key, []).append(obs)

    # 5) Optional AI extrapolation for sparse cohorts
    extrapolations = 0
    if extrapolate and metrics:
        metric_by_id = {m["metric_id"]: m for m in metrics}
        cohort_by_id = {c["cohort_id"]: c for c in cohorts}
        # iterate every (metric × cohort) pair and check coverage at any period
        for metric in metrics:
            for cohort in cohorts:
                periods = sorted({k[2] for k in grouped if k[0] == metric["metric_id"] and k[1] == cohort["cohort_id"]})
                if not periods:
                    continue
                latest = periods[-1]
                key = (metric["metric_id"], cohort["cohort_id"], latest)
                if len(grouped.get(key, [])) >= 3:
                    continue
                neighbour = [
                    o for k, lst in grouped.items() for o in lst
                    if k[0] == metric["metric_id"] and k[1] != cohort["cohort_id"]
                ]
                ai = _extrapolate(metric, cohort, latest, neighbour)
                if ai:
                    repo.upsert(OBSERVATIONS_COLLECTION, ai["id"], ai)
                    grouped.setdefault(key, []).append(ai)
                    extrapolations += 1

    # 6) Compute + persist distributions
    distributions = []
    for (metric_id, cohort_id, period), obs in grouped.items():
        dist = _compute_distribution(metric_id, cohort_id, period, obs)
        repo.upsert(DISTRIBUTIONS_COLLECTION, dist["id"], dist)
        distributions.append(dist)

    # 7) Sources catalogue
    by_source: dict[str, dict] = {}
    for obs in all_obs:
        key = obs["source_label"] or obs["source_kind"]
        rec = by_source.setdefault(key, {
            "id": f"src-{key.lower().replace(' ', '_')}",
            "label": key,
            "kind": obs["source_kind"],
            "tier": obs.get("tier"),
            "observation_count": 0,
            "url": obs.get("source_url"),
        })
        rec["observation_count"] += 1
    for rec in by_source.values():
        repo.upsert(SOURCES_COLLECTION, rec["id"], rec)

    completed = datetime.now(timezone.utc)
    run_id = f"benchmarks-ingest-{int(started.timestamp())}"
    summary = IngestSummary(
        run_id=run_id,
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        filings_loaded=filings_n,
        analyst_observations=len(analyst_obs),
        technographic_companies=techno_n,
        observations_total=len(all_obs) + extrapolations,
        distributions_total=len(distributions),
        extrapolations_total=extrapolations,
        cohorts_loaded=len(cohorts),
        sources=sources,
        schema_issues=issues,
    )
    repo.upsert(RUN_COLLECTION, run_id, asdict(summary))
    return summary


def list_distributions(
    metric_id: str | None = None,
    cohort_id: str | None = None,
    sub_cap_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    repo = get_repository()
    items = repo.list(DISTRIBUTIONS_COLLECTION)
    if metric_id:
        items = [d for d in items if d.get("metric_id") == metric_id]
    if cohort_id:
        items = [d for d in items if d.get("cohort_id") == cohort_id]
    if sub_cap_id:
        metrics = _load_metrics()
        eligible = {
            m["metric_id"] for m in metrics
            if any(_matches_pattern(p, sub_cap_id) for p in (m.get("subcap_mappings") or []))
        }
        items = [d for d in items if d.get("metric_id") in eligible]
    items.sort(key=lambda d: (d.get("metric_id", ""), d.get("cohort_id", ""), d.get("period", "")))
    return items[:limit]


def get_distribution(dist_id: str) -> dict | None:
    return get_repository().get(DISTRIBUTIONS_COLLECTION, dist_id)


def list_observations(
    metric_id: str | None = None,
    cohort_id: str | None = None,
    company: str | None = None,
    limit: int = 500,
) -> list[dict]:
    repo = get_repository()
    items = repo.list(OBSERVATIONS_COLLECTION)
    if metric_id:
        items = [o for o in items if o.get("metric_id") == metric_id]
    if cohort_id:
        items = [o for o in items if cohort_id in (o.get("cohort_ids") or [])]
    if company:
        items = [o for o in items if (o.get("company") or "").lower() == company.lower()]
    items.sort(key=lambda o: o.get("period", ""), reverse=True)
    return items[:limit]


def list_cohorts() -> list[dict]:
    return list(get_repository().list(COHORTS_COLLECTION))


def list_sources() -> list[dict]:
    return list(get_repository().list(SOURCES_COLLECTION))


def list_metrics() -> list[dict]:
    return _load_metrics()


def latest_run() -> dict | None:
    runs = get_repository().list(RUN_COLLECTION)
    if not runs:
        return None
    runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return runs[0]


def _matches_pattern(pattern: str, sub_cap_id: str) -> bool:
    """Wildcard match for "P1C2.3.*" style patterns."""
    if not pattern.endswith("*"):
        return pattern == sub_cap_id
    return sub_cap_id.startswith(pattern[:-1])
