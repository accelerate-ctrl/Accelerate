"""Cloud Run Job: digest_quarterly.

Generates a Strategic Digest for every configured subvertical for the
current quarter (or the period passed via --arg period=…). Quarterly
cadence; uses Claude Opus narratives via the Batch-4 consultant loop.
"""

from __future__ import annotations

from datetime import date

from ..services import digest_service
from ..services.event_bus import publish_event

DEFAULT_SUBVERTICALS = (
    "retail-banking",
    "wealth-management",
    "insurance-life-annuity",
    "credit-unions",
    "commercial-lending",
    "asset-management",
)


def _current_quarter() -> str:
    today = date.today()
    q = (today.month - 1) // 3 + 1
    return f"{today.year}-Q{q}"


def run(*, period: str | None = None, priority_limit: int = 5, subverticals: str | None = None) -> dict:
    target_period = period or _current_quarter()
    target_svs = subverticals.split(",") if subverticals else DEFAULT_SUBVERTICALS
    generated: list[dict] = []
    for sv in target_svs:
        digest = digest_service.generate(
            subvertical=sv, period=target_period, priority_limit=priority_limit,
        )
        generated.append({
            "digest_id": digest.digest_id,
            "subvertical": sv,
            "priorities": len(digest.priorities),
            "cost_usd": digest.total_cost_usd,
        })
        publish_event(
            "digest.generated",
            {"digest_id": digest.digest_id, "subvertical": sv, "period": target_period},
        )
    return {"period": target_period, "digests": generated}
