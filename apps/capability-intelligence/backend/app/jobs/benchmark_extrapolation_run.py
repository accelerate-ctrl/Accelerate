"""Cloud Run Job: benchmark_extrapolation_run.

Triggers the AI-extrapolation pass for sparse cohorts. Weekly cadence;
each cohort with N<3 observations gets one consultant-loop call on
Gemini-Pro. Cost-bounded by the LLM router's budget guardrails.
"""

from __future__ import annotations

from dataclasses import asdict

from ..services import benchmarks_service


def run() -> dict:
    summary = benchmarks_service.refresh(extrapolate=True)
    return asdict(summary)
