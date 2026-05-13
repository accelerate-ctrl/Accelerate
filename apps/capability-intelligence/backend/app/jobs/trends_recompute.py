"""Cloud Run Job: trends_recompute.

K-Means clusters the last 30 days of news items into trend groups,
summarises each with Gemini Flash (one cheap call per cluster), and
persists the result to the `trend_clusters` collection.

Scheduled daily; the cluster-summary cost is small (≈ 8 calls/day ≈
$0.002/day) and the cluster set rotates with the news mix.

    cron: 0 5 * * *   # daily 05:00 UTC
"""

from __future__ import annotations

from ..services import trends_service


def run() -> dict:
    return trends_service.recompute_clusters(k=8, lookback_days=30)
