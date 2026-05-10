"""Cloud Run Job: benchmark_recompute_quarterly.

Forces a full benchmark refresh + extrapolation + distribution
recompute. Quarterly cadence (aligned to filing season).
"""

from __future__ import annotations

from dataclasses import asdict

from ..services import benchmarks_service


def run() -> dict:
    summary = benchmarks_service.refresh(extrapolate=True)
    return asdict(summary)
