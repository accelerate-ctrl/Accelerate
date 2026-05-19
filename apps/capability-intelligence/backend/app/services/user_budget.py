"""Per-user daily token budget (IMP-9).

Background — Implementation Steps §3 IMP-9: a single aggressive user
running 50 chat queries / day with complex context can consume
$40–80 of the monthly envelope. The global cost meter doesn't
prevent this; per-user budgets do.

Behaviour:

- Each user gets a configurable daily ceiling (default ``$5/user/day``;
  override via ``DEFAULT_USER_DAILY_BUDGET_USD`` env or admin patch).
- Spend is rolled up by ``(user_email, YYYY-MM-DD)`` so the counter
  resets at UTC midnight.
- When the cap is hit, ``decision_for(user_email)`` returns
  ``{should_downgrade: True}`` so the LLM router can fall back from
  Gemini Pro / Sonnet to Gemini Flash for the rest of the day.
- Admins listed in ``ADMIN_EMAILS`` bypass the cap (the ``admin``
  bool on the decision lets caller services log the override).

The service is intentionally separate from :class:`CostTracker` —
that module owns the global envelope; this one owns the per-user
slice. The LLM router can consult both.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .repository import get_repository

logger = logging.getLogger(__name__)

USER_SPEND_COLLECTION = "user_daily_spend"
USER_BUDGET_OVERRIDES = "user_budget_overrides"
USER_BUDGET_AUDIT = "user_budget_audit"

# Default ceiling per user per day. Env override supports lifting the
# cap site-wide without a code deploy.
def _default_daily_budget_usd() -> float:
    raw = os.environ.get("DEFAULT_USER_DAILY_BUDGET_USD")
    if raw:
        try:
            return float(raw)
        except ValueError:
            logger.warning(
                "invalid DEFAULT_USER_DAILY_BUDGET_USD=%s; falling back to 5.0",
                raw,
            )
    return 5.0


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _doc_id(user_email: str, day: str | None = None) -> str:
    return f"{(user_email or 'anon').lower()}::{day or _today_utc()}"


# ─── Data shapes ──────────────────────────────────────────────────────────


@dataclass
class UserSpend:
    """Persisted per-user-per-day spend row."""

    user_email: str
    day: str  # YYYY-MM-DD
    spend_usd: float = 0.0
    call_count: int = 0
    last_updated: str = ""


@dataclass
class BudgetDecision:
    """Returned by :func:`decision_for` so the LLM router can adapt."""

    user_email: str
    day: str
    spend_usd: float
    budget_usd: float
    fraction: float
    should_downgrade: bool  # True once spend ≥ budget
    admin_override: bool
    headroom_usd: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── Admin allow-list (IMP-9 admin override path) ──────────────────────────


def _is_admin(user_email: str) -> bool:
    raw = os.environ.get("ADMIN_EMAILS", "")
    allowed = {a.strip().lower() for a in raw.split(",") if a.strip()}
    return (user_email or "").lower() in allowed


# ─── Overrides — admins can set a custom budget for one user ───────────────


def set_user_budget_override(
    user_email: str, *, daily_budget_usd: float, set_by: str,
) -> dict[str, Any]:
    """Admin-set override of one user's daily budget. Persisted so the
    override survives restarts; audit row captures who set it + when.
    """
    repo = get_repository()
    row = {
        "user_email": user_email.lower(),
        "daily_budget_usd": float(daily_budget_usd),
        "set_at": datetime.now(timezone.utc).isoformat(),
        "set_by": set_by,
    }
    repo.upsert(USER_BUDGET_OVERRIDES, user_email.lower(), row)
    audit_id = f"audit-{int(datetime.now(timezone.utc).timestamp() * 1_000)}-{user_email.lower()}"
    repo.upsert(USER_BUDGET_AUDIT, audit_id, {
        "id": audit_id,
        "kind": "override_set",
        **row,
    })
    return row


def clear_user_budget_override(user_email: str, *, cleared_by: str) -> bool:
    """Remove a user's override so they drop back to the default."""
    repo = get_repository()
    existing = repo.get(USER_BUDGET_OVERRIDES, user_email.lower())
    if not existing:
        return False
    repo.delete(USER_BUDGET_OVERRIDES, user_email.lower())
    audit_id = f"audit-{int(datetime.now(timezone.utc).timestamp() * 1_000)}-{user_email.lower()}-clear"
    repo.upsert(USER_BUDGET_AUDIT, audit_id, {
        "id": audit_id,
        "kind": "override_cleared",
        "user_email": user_email.lower(),
        "cleared_at": datetime.now(timezone.utc).isoformat(),
        "cleared_by": cleared_by,
        "prior_budget_usd": existing.get("daily_budget_usd"),
    })
    return True


def budget_for(user_email: str) -> float:
    """Resolve the daily budget for one user.

    Override > env default. The override stays until an admin clears
    it; the env default applies to every user without one.
    """
    repo = get_repository()
    override = repo.get(USER_BUDGET_OVERRIDES, (user_email or "").lower())
    if override and isinstance(override.get("daily_budget_usd"), (int, float)):
        return float(override["daily_budget_usd"])
    return _default_daily_budget_usd()


# ─── Spend bookkeeping ────────────────────────────────────────────────────


def record_spend(user_email: str, *, cost_usd: float) -> UserSpend:
    """Add a single LLM-call cost to the user's daily roll-up.

    Cost ≤ 0 is a no-op so call sites can be safely instrumented
    without needing to check the cost themselves.
    """
    if not user_email or cost_usd <= 0:
        return UserSpend(
            user_email=(user_email or "anon").lower(),
            day=_today_utc(),
            spend_usd=0.0,
            call_count=0,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )
    repo = get_repository()
    day = _today_utc()
    doc_id = _doc_id(user_email, day)
    existing = repo.get(USER_SPEND_COLLECTION, doc_id) or {}
    spend = float(existing.get("spend_usd") or 0.0) + float(cost_usd)
    count = int(existing.get("call_count") or 0) + 1
    row = UserSpend(
        user_email=(user_email or "anon").lower(),
        day=day,
        spend_usd=round(spend, 6),
        call_count=count,
        last_updated=datetime.now(timezone.utc).isoformat(),
    )
    repo.upsert(USER_SPEND_COLLECTION, doc_id, asdict(row))
    return row


def spend_for(user_email: str, *, day: str | None = None) -> UserSpend:
    """Read the current spend row for a user/day (zero-row if absent)."""
    repo = get_repository()
    day = day or _today_utc()
    row = repo.get(USER_SPEND_COLLECTION, _doc_id(user_email, day))
    if not row:
        return UserSpend(
            user_email=(user_email or "anon").lower(),
            day=day,
            spend_usd=0.0,
            call_count=0,
            last_updated="",
        )
    return UserSpend(
        user_email=row.get("user_email", (user_email or "anon").lower()),
        day=row.get("day", day),
        spend_usd=float(row.get("spend_usd") or 0.0),
        call_count=int(row.get("call_count") or 0),
        last_updated=row.get("last_updated", ""),
    )


# ─── The decision the LLM router consults before each call ────────────────


def decision_for(user_email: str) -> BudgetDecision:
    """Should the next LLM call for this user run at full quality, or
    downgrade to Flash?

    Admins always run at full quality (the ``admin_override`` field on
    the response lets the call site log the override so cost is still
    visible).
    """
    budget = budget_for(user_email)
    spend = spend_for(user_email).spend_usd
    fraction = (spend / budget) if budget > 0 else 0.0
    admin = _is_admin(user_email)
    should_downgrade = (not admin) and spend >= budget
    headroom = max(0.0, budget - spend)
    return BudgetDecision(
        user_email=(user_email or "anon").lower(),
        day=_today_utc(),
        spend_usd=round(spend, 6),
        budget_usd=round(budget, 6),
        fraction=round(fraction, 4),
        should_downgrade=should_downgrade,
        admin_override=admin,
        headroom_usd=round(headroom, 6),
    )


def top_spenders(*, day: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
    """List today's top spenders for the QA dashboard."""
    day = day or _today_utc()
    repo = get_repository()
    rows = [
        r for r in repo.list(USER_SPEND_COLLECTION)
        if r.get("day") == day
    ]
    rows.sort(key=lambda r: float(r.get("spend_usd") or 0.0), reverse=True)
    return rows[:limit]


def list_overrides() -> list[dict[str, Any]]:
    """All active per-user overrides."""
    return list(get_repository().list(USER_BUDGET_OVERRIDES))


def list_audit(limit: int = 100) -> list[dict[str, Any]]:
    rows = list(get_repository().list(USER_BUDGET_AUDIT))
    rows.sort(key=lambda r: r.get("set_at") or r.get("cleared_at") or "", reverse=True)
    return rows[:limit]


__all__ = [
    "BudgetDecision",
    "USER_BUDGET_AUDIT",
    "USER_BUDGET_OVERRIDES",
    "USER_SPEND_COLLECTION",
    "UserSpend",
    "budget_for",
    "clear_user_budget_override",
    "decision_for",
    "list_audit",
    "list_overrides",
    "record_spend",
    "set_user_budget_override",
    "spend_for",
    "top_spenders",
]
