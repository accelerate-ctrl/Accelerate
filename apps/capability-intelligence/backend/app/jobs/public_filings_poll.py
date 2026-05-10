"""Cloud Run Job: public_filings_poll.

Polls SEC EDGAR / FDIC / Form ADV / analyst extracts via the
``benchmarks_service`` ingest path. Daily cadence.
"""

from __future__ import annotations

from dataclasses import asdict

from ..services import benchmarks_service


def run() -> dict:
    summary = benchmarks_service.refresh(extrapolate=False)
    return asdict(summary)
