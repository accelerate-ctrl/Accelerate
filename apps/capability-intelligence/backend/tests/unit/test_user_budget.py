"""Per-user daily token budget tests (Phase 5.2 / IMP-9)."""

import pytest

from app.services import user_budget
from app.services.user_budget import (
    USER_BUDGET_OVERRIDES,
    USER_SPEND_COLLECTION,
    budget_for,
    clear_user_budget_override,
    decision_for,
    list_audit,
    list_overrides,
    record_spend,
    set_user_budget_override,
    spend_for,
    top_spenders,
)
from app.services.repository import get_repository


@pytest.fixture(autouse=True)
def _budget_env(monkeypatch):
    """Pin the default budget + admin list so tests are deterministic."""
    monkeypatch.setenv("DEFAULT_USER_DAILY_BUDGET_USD", "5.0")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@zen.co")


# ─── Spend bookkeeping ────────────────────────────────────────────────────


def test_record_spend_accumulates(settings_for_tests):
    a = record_spend("alice@zen.co", cost_usd=0.50)
    assert a.spend_usd == 0.50
    assert a.call_count == 1
    b = record_spend("alice@zen.co", cost_usd=1.25)
    assert b.spend_usd == 1.75
    assert b.call_count == 2


def test_record_spend_ignores_zero_and_negative(settings_for_tests):
    record_spend("alice@zen.co", cost_usd=0.0)
    record_spend("alice@zen.co", cost_usd=-1.0)
    assert spend_for("alice@zen.co").spend_usd == 0.0


def test_record_spend_per_user_isolated(settings_for_tests):
    record_spend("alice@zen.co", cost_usd=1.0)
    record_spend("bob@zen.co", cost_usd=2.0)
    assert spend_for("alice@zen.co").spend_usd == 1.0
    assert spend_for("bob@zen.co").spend_usd == 2.0


def test_spend_for_absent_user_returns_zero(settings_for_tests):
    row = spend_for("never-spent@zen.co")
    assert row.spend_usd == 0.0
    assert row.call_count == 0


def test_email_normalised_to_lowercase(settings_for_tests):
    record_spend("Alice@Zen.Co", cost_usd=1.0)
    # Spend should be retrievable regardless of case.
    assert spend_for("alice@zen.co").spend_usd == 1.0
    assert spend_for("ALICE@ZEN.CO").spend_usd == 1.0


# ─── Decision logic ───────────────────────────────────────────────────────


def test_decision_under_budget_does_not_downgrade(settings_for_tests):
    record_spend("alice@zen.co", cost_usd=1.0)
    d = decision_for("alice@zen.co")
    assert d.should_downgrade is False
    assert d.spend_usd == 1.0
    assert d.headroom_usd == 4.0


def test_decision_at_budget_downgrades(settings_for_tests):
    record_spend("alice@zen.co", cost_usd=5.0)
    d = decision_for("alice@zen.co")
    assert d.should_downgrade is True
    assert d.fraction == 1.0
    assert d.headroom_usd == 0.0


def test_decision_over_budget_downgrades(settings_for_tests):
    record_spend("alice@zen.co", cost_usd=10.0)
    d = decision_for("alice@zen.co")
    assert d.should_downgrade is True
    assert d.fraction == 2.0


def test_admin_user_bypasses_cap(settings_for_tests):
    record_spend("admin@zen.co", cost_usd=100.0)
    d = decision_for("admin@zen.co")
    assert d.should_downgrade is False
    assert d.admin_override is True


def test_admin_email_lookup_is_case_insensitive(settings_for_tests):
    record_spend("Admin@Zen.Co", cost_usd=999.0)
    d = decision_for("Admin@Zen.Co")
    assert d.admin_override is True


def test_zero_budget_means_immediate_downgrade(monkeypatch, settings_for_tests):
    """A site-wide budget of 0 effectively turns every user into a
    Flash-only path. Verify the math doesn't divide by zero."""
    monkeypatch.setenv("DEFAULT_USER_DAILY_BUDGET_USD", "0")
    d = decision_for("alice@zen.co")
    # No spend yet, budget 0 → should_downgrade is False (spend !>= budget==0).
    # spend < budget condition flips to >=, and 0 >= 0 is True → downgrade.
    assert d.budget_usd == 0.0
    assert d.should_downgrade is True


# ─── Overrides ────────────────────────────────────────────────────────────


def test_set_override_changes_budget(settings_for_tests):
    set_user_budget_override("alice@zen.co", daily_budget_usd=20.0, set_by="admin")
    assert budget_for("alice@zen.co") == 20.0
    # Other users still see the default.
    assert budget_for("bob@zen.co") == 5.0


def test_clear_override_restores_default(settings_for_tests):
    set_user_budget_override("alice@zen.co", daily_budget_usd=20.0, set_by="admin")
    ok = clear_user_budget_override("alice@zen.co", cleared_by="admin")
    assert ok is True
    assert budget_for("alice@zen.co") == 5.0


def test_clear_unknown_override_returns_false(settings_for_tests):
    assert clear_user_budget_override("nobody@zen.co", cleared_by="admin") is False


def test_override_audit_log_records_change(settings_for_tests):
    set_user_budget_override("alice@zen.co", daily_budget_usd=10.0, set_by="op-1")
    clear_user_budget_override("alice@zen.co", cleared_by="op-2")
    audit = list_audit()
    kinds = [a["kind"] for a in audit]
    # Two events recorded — set + clear.
    assert "override_set" in kinds
    assert "override_cleared" in kinds


def test_override_persists_in_dedicated_collection(settings_for_tests):
    set_user_budget_override("alice@zen.co", daily_budget_usd=15.0, set_by="op")
    rows = list_overrides()
    assert len(rows) == 1
    assert rows[0]["user_email"] == "alice@zen.co"
    assert rows[0]["daily_budget_usd"] == 15.0


# ─── Top-spenders + audit list ────────────────────────────────────────────


def test_top_spenders_sorted_desc(settings_for_tests):
    record_spend("alice@zen.co", cost_usd=2.0)
    record_spend("bob@zen.co", cost_usd=10.0)
    record_spend("carol@zen.co", cost_usd=0.5)
    rows = top_spenders()
    emails = [r["user_email"] for r in rows]
    assert emails[:3] == ["bob@zen.co", "alice@zen.co", "carol@zen.co"]


def test_top_spenders_limit_respected(settings_for_tests):
    for i in range(10):
        record_spend(f"u{i}@zen.co", cost_usd=float(i + 1))
    rows = top_spenders(limit=3)
    assert len(rows) == 3


# ─── Cross-day isolation ──────────────────────────────────────────────────


def test_spend_keyed_by_day(settings_for_tests):
    """Spends from yesterday must not roll into today's decision."""
    repo = get_repository()
    repo.upsert(USER_SPEND_COLLECTION, "alice@zen.co::2026-01-01", {
        "user_email": "alice@zen.co",
        "day": "2026-01-01",
        "spend_usd": 999.0,
        "call_count": 1000,
        "last_updated": "2026-01-01T08:00:00Z",
    })
    # Today's decision sees zero spend.
    d = decision_for("alice@zen.co")
    assert d.spend_usd == 0.0
    assert d.should_downgrade is False


def test_default_budget_env_override(monkeypatch, settings_for_tests):
    monkeypatch.setenv("DEFAULT_USER_DAILY_BUDGET_USD", "25.5")
    assert budget_for("anyone@zen.co") == 25.5


def test_invalid_env_default_falls_back(monkeypatch, settings_for_tests):
    monkeypatch.setenv("DEFAULT_USER_DAILY_BUDGET_USD", "not-a-number")
    assert budget_for("anyone@zen.co") == 5.0


# ─── BudgetDecision dataclass serialisation ───────────────────────────────


def test_decision_to_dict_round_trip(settings_for_tests):
    record_spend("alice@zen.co", cost_usd=2.5)
    d = decision_for("alice@zen.co").to_dict()
    assert d["user_email"] == "alice@zen.co"
    assert d["spend_usd"] == 2.5
    assert d["budget_usd"] == 5.0
    assert d["should_downgrade"] is False
