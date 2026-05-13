"""Cloud Run Job: news_impact_synthesis.

Runs Gemini Flash impact classification on news items that don't already
carry an `impact` block. Capped at 50 items per run (≈ $0.015 of Gemini
spend at standard pricing) per the operator-confirmed weekly cadence.

Scheduled by Cloud Scheduler:
    cron: 0 6 * * 1   # Monday 06:00 UTC
"""

from __future__ import annotations

from ..services import news_service


def run() -> dict:
    return news_service.synthesise_impact_batch(limit=50, force=False)
