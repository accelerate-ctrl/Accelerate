"""Cost tracker — daily + weekly spend with budget enforcement.

Records every adapter call (model, input_tokens, output_tokens, $) into the
``llm_costs`` collection.  ``assert_within_budget()`` raises
:class:`BudgetExceeded` when the daily ceiling is hit at or above
``cost_throttle_pct`` (default 90%).

In prod we'd swap this to BigQuery ``cost_tracking`` — same write surface,
different sink.  Reads (``spend_today``, ``spend_this_week``) are O(N)
over today/this-week's entries, which is fine at the volumes we expect
(<10k calls/day).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from ...config import get_settings
from ..repository import get_repository

if TYPE_CHECKING:
    from .router import ModelKind

COST_COLLECTION = "llm_costs"


class BudgetExceeded(RuntimeError):
    """Raised when the daily / weekly ceiling has been hit."""


@dataclass
class CostSummary:
    today_usd: float
    week_usd: float
    today_calls: int
    week_calls: int
    by_model: dict[str, float]


class CostTracker:
    def record(
        self,
        model: ModelKind,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> None:
        repo = get_repository()
        now = datetime.now(timezone.utc)
        rec_id = f"cost-{int(now.timestamp() * 1_000_000)}-{model.value}"
        repo.upsert(
            COST_COLLECTION,
            rec_id,
            {
                "id": rec_id,
                "model": model.value,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": float(cost_usd),
                "ts": now.isoformat(),
                "day": now.date().isoformat(),
            },
        )

    def spend_today(self) -> float:
        today = date.today().isoformat()
        return sum(
            float(r.get("cost_usd", 0.0))
            for r in get_repository().list(COST_COLLECTION)
            if r.get("day") == today
        )

    def spend_in_week(self) -> float:
        cutoff = date.today() - timedelta(days=6)
        return sum(
            float(r.get("cost_usd", 0.0))
            for r in get_repository().list(COST_COLLECTION)
            if r.get("day", "") >= cutoff.isoformat()
        )

    def summary(self) -> CostSummary:
        today = date.today().isoformat()
        week_cutoff = (date.today() - timedelta(days=6)).isoformat()
        recs = get_repository().list(COST_COLLECTION)
        today_recs = [r for r in recs if r.get("day") == today]
        week_recs = [r for r in recs if r.get("day", "") >= week_cutoff]
        by_model: dict[str, float] = {}
        for r in week_recs:
            m = r.get("model", "?")
            by_model[m] = by_model.get(m, 0.0) + float(r.get("cost_usd", 0.0))
        return CostSummary(
            today_usd=sum(float(r.get("cost_usd", 0.0)) for r in today_recs),
            week_usd=sum(float(r.get("cost_usd", 0.0)) for r in week_recs),
            today_calls=len(today_recs),
            week_calls=len(week_recs),
            by_model=by_model,
        )

    def assert_within_budget(self) -> None:
        s = get_settings()
        if s.daily_spend_ceiling_usd > 0:
            spent = self.spend_today()
            cap = s.daily_spend_ceiling_usd * s.cost_throttle_pct
            if spent >= cap:
                raise BudgetExceeded(
                    f"daily spend ${spent:.2f} ≥ {s.cost_throttle_pct * 100:.0f}% of "
                    f"${s.daily_spend_ceiling_usd:.2f} ceiling"
                )
        if s.anthropic_weekly_budget_usd > 0:
            spent = self.spend_in_week()
            if spent >= s.anthropic_weekly_budget_usd * s.cost_throttle_pct:
                raise BudgetExceeded(
                    f"weekly Anthropic spend ${spent:.2f} hit {s.cost_throttle_pct * 100:.0f}% of "
                    f"${s.anthropic_weekly_budget_usd:.2f} budget — degrading to Gemini until reset"
                )

    def clear(self) -> None:
        repo = get_repository()
        for r in list(repo.list(COST_COLLECTION)):
            repo.delete(COST_COLLECTION, r.get("id", ""))
