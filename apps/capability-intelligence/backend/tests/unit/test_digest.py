"""Quarterly Strategic Digest generation."""

import pytest

from app.services import (
    benchmarks_service,
    digest_service,
    lifecycle_service,
    news_service,
)
from app.services.digest_service import _previous_period
from app.services.llm.router import reset_state_for_tests


@pytest.fixture
def seeded(settings_for_tests):
    from app.services import catalogue_service, sow_service, stories_service
    catalogue_service.refresh_pillar("P1", by="test")
    sow_service.ingest_all()
    stories_service.refresh_all()
    benchmarks_service.refresh(extrapolate=False)
    news_service.refresh()
    lifecycle_service.recompute_all()
    reset_state_for_tests()
    return settings_for_tests


def test_previous_period_quarter_arithmetic():
    assert _previous_period("2026-Q2") == "2026-Q1"
    assert _previous_period("2026-Q1") == "2025-Q4"
    assert _previous_period("2025-Q4") == "2025-Q3"
    assert _previous_period("garbage") is None
    assert _previous_period(None) is None


def test_generate_returns_priorities(seeded):
    digest = digest_service.generate(
        subvertical="retail-banking", period="2026-Q2", priority_limit=3,
    )
    # at least one RISING priority lands (Wells Fargo P1C1.1.1)
    assert digest.priorities
    head = digest.priorities[0]
    assert head["state"] in ("RISING", "STABLE", "EMERGING")
    assert head["narrative"]
    assert head["recommendation"]
    assert digest.summary
    assert digest.previous_period == "2026-Q1"
    assert digest.subvertical == "retail-banking"


def test_generate_persists(seeded):
    digest = digest_service.generate(
        subvertical="retail-banking", period="2026-Q2", priority_limit=3,
    )
    fetched = digest_service.get_digest(digest.digest_id)
    assert fetched is not None
    assert fetched["digest_id"] == digest.digest_id


def test_generate_attaches_evidence(seeded):
    digest = digest_service.generate(
        subvertical="retail-banking", period="2026-Q2", priority_limit=5,
    )
    head = digest.priorities[0]
    # Wells Fargo SOW + benchmark + news evidence should attach
    assert any(e for e in head["evidence_sows"]) or any(e for e in head["evidence_benchmarks"]) \
        or any(e for e in head["evidence_news"]), "expected at least one evidence row"


def test_generate_q_over_q_delta(seeded):
    # Run two consecutive quarters → second one carries delta vs first
    digest_service.generate(
        subvertical="retail-banking", period="2026-Q1", priority_limit=3,
    )
    digest = digest_service.generate(
        subvertical="retail-banking", period="2026-Q2", priority_limit=3,
    )
    has_delta = any(p.get("delta") and p["delta"].get("previous_period") for p in digest.priorities)
    assert has_delta, "expected at least one priority with previous-period delta"


def test_generate_unknown_subvertical_returns_empty(seeded):
    digest = digest_service.generate(
        subvertical="nonexistent-subvertical", period="2026-Q2", priority_limit=3,
    )
    # graceful degradation: no priorities, but a summary describing the empty state
    assert digest.priorities == []
    assert "No actionable priorities" in digest.summary


def test_list_digests_filters_by_subvertical(seeded):
    digest_service.generate(subvertical="retail-banking", period="2026-Q2")
    digest_service.generate(subvertical="wealth-management", period="2026-Q2")
    only_rb = digest_service.list_digests(subvertical="retail-banking")
    assert all(d["subvertical"] == "retail-banking" for d in only_rb)
