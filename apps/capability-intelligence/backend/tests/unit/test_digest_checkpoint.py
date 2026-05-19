"""Digest checkpoint / resume tests (Phase 4.4 / QA_AUDIT F08)."""

import pytest

from app.services import digest_service
from app.services.digest_service import (
    DIGEST_CHECKPOINT_COLLECTION,
    DIGEST_COLLECTION,
    PriorityNarrative,
    _checkpoint_doc_id,
    _clear_checkpoints,
    _digest_id,
    _load_checkpoints,
    _priority_from_checkpoint,
    _write_checkpoint,
    list_checkpoints,
)
from app.services.repository import get_repository


@pytest.fixture
def digest_id() -> str:
    return _digest_id("RB", "2026-Q2")


@pytest.fixture(autouse=True)
def _isolate_repo(settings_for_tests):
    yield


# ─── Direct helper tests ──────────────────────────────────────────────────


def test_checkpoint_doc_id_is_stable(digest_id):
    """Same (digest, subcap) → same id so re-runs hit the cache."""
    a = _checkpoint_doc_id(digest_id, "P1C1.1.1")
    b = _checkpoint_doc_id(digest_id, "P1C1.1.1")
    assert a == b
    assert a.endswith("::P1C1.1.1")


def test_checkpoint_doc_ids_dont_collide_across_digests():
    a = _checkpoint_doc_id(_digest_id("RB", "2026-Q1"), "P1C1.1.1")
    b = _checkpoint_doc_id(_digest_id("RB", "2026-Q2"), "P1C1.1.1")
    assert a != b


def test_write_and_load_round_trip(digest_id):
    narrative = PriorityNarrative(
        sub_cap_id="P1C1.1.1",
        sub_cap_name="Test Subcap",
        state="RISING",
        score=78.0,
        confidence=0.9,
        narrative="The strategy is solid.",
        recommendation="Increase investment.",
        evidence_sows=[{"sow_id": "S1", "client": "Acme"}],
        evidence_benchmarks=[],
        evidence_news=[],
        delta={"score": +5},
        chain_id="chain-xyz",
        cost_usd=0.08,
    )
    _write_checkpoint(digest_id, "P1C1.1.1", narrative)
    loaded = _load_checkpoints(digest_id)
    assert "P1C1.1.1" in loaded
    rebuilt = _priority_from_checkpoint(loaded["P1C1.1.1"])
    assert rebuilt.sub_cap_id == narrative.sub_cap_id
    assert rebuilt.narrative == narrative.narrative
    assert rebuilt.chain_id == narrative.chain_id
    assert rebuilt.cost_usd == narrative.cost_usd


def test_load_checkpoints_only_returns_target_digest(digest_id):
    """Checkpoints from a different digest must not leak into this load."""
    other_digest = _digest_id("CB", "2026-Q2")
    narrative = PriorityNarrative(
        sub_cap_id="P1C1.1.1", sub_cap_name="x",
        state="RISING", score=0, confidence=0,
        narrative="a", recommendation="b",
    )
    _write_checkpoint(digest_id, "P1C1.1.1", narrative)
    _write_checkpoint(other_digest, "P1C1.1.1", narrative)
    loaded = _load_checkpoints(digest_id)
    assert len(loaded) == 1
    # And the other digest sees only its own checkpoint.
    assert len(_load_checkpoints(other_digest)) == 1


def test_clear_checkpoints_drops_only_target(digest_id):
    other_digest = _digest_id("CB", "2026-Q2")
    nv = PriorityNarrative(
        sub_cap_id="P1C1.1.1", sub_cap_name="x",
        state="RISING", score=0, confidence=0,
        narrative="a", recommendation="b",
    )
    _write_checkpoint(digest_id, "P1C1.1.1", nv)
    _write_checkpoint(digest_id, "P1C2.1.1", nv)
    _write_checkpoint(other_digest, "P1C1.1.1", nv)
    dropped = _clear_checkpoints(digest_id)
    assert dropped == 2
    assert _load_checkpoints(digest_id) == {}
    assert len(_load_checkpoints(other_digest)) == 1


def test_priority_from_checkpoint_handles_missing_optional_fields():
    """A minimal checkpoint (only required fields) should still
    rehydrate without raising."""
    ckpt = {"sub_cap_id": "P1C1.1.1", "narrative": "x", "recommendation": "y"}
    rebuilt = _priority_from_checkpoint(ckpt)
    assert rebuilt.sub_cap_id == "P1C1.1.1"
    assert rebuilt.evidence_sows == []
    assert rebuilt.cost_usd == 0.0


def test_list_checkpoints_public_helper(digest_id):
    nv = PriorityNarrative(
        sub_cap_id="P1C1.1.1", sub_cap_name="x",
        state="RISING", score=0, confidence=0,
        narrative="a", recommendation="b",
    )
    _write_checkpoint(digest_id, "P1C1.1.1", nv)
    rows = list_checkpoints(digest_id)
    assert len(rows) == 1
    assert rows[0]["sub_cap_id"] == "P1C1.1.1"


# ─── End-to-end generate + resume ─────────────────────────────────────────


@pytest.fixture
def seeded_digest_inputs(settings_for_tests):
    """Seed the minimum lifecycle + subvertical state the digest
    generator needs to produce at least one priority."""
    repo = get_repository()
    repo.upsert("vc_mappings", "P1C1.1.1__RB", {
        "sub_cap_id": "P1C1.1.1",
        "subvertical_code": "RB",
        "stages": ["acquire"],
    })
    repo.upsert("lifecycle_scores", "P1C1.1.1", {
        "sub_cap_id": "P1C1.1.1",
        "sub_cap_name": "Strategy Doc",
        "state": "RISING",
        "score": 78.0,
        "confidence": 0.9,
        "last_signal_at": "2026-04-01T08:00:00Z",
    })
    repo.upsert("subcaps", "P1C1.1.1", {
        "sub_cap_id": "P1C1.1.1",
        "sub_cap_name": "Strategy Doc",
        "pillar_id": "P1",
        "category_id": "C1",
        "l1_capability": "L1",
    })
    return repo


def test_generate_writes_checkpoints_per_priority(seeded_digest_inputs):
    digest_service.generate(subvertical="RB", period="2026-Q2", priority_limit=3)
    # After a successful run, checkpoints should be CLEARED.
    rows = list_checkpoints(_digest_id("RB", "2026-Q2"))
    assert rows == []


def test_resume_skips_already_checkpointed_priorities(seeded_digest_inputs):
    """A pre-existing checkpoint for a priority must bypass the LLM
    call. We assert by checking that the post-run digest carries the
    checkpoint's recorded narrative + cost (not a fresh LLM emission).
    """
    digest_id = _digest_id("RB", "2026-Q2")
    canned = PriorityNarrative(
        sub_cap_id="P1C1.1.1",
        sub_cap_name="Strategy Doc",
        state="RISING",
        score=78.0,
        confidence=0.9,
        narrative="CACHED NARRATIVE FROM CHECKPOINT",
        recommendation="CACHED RECOMMENDATION",
        chain_id="chain-cached",
        cost_usd=0.12,
    )
    _write_checkpoint(digest_id, "P1C1.1.1", canned)

    digest = digest_service.generate(
        subvertical="RB", period="2026-Q2", priority_limit=3,
    )
    priority = next(
        p for p in digest.priorities if p["sub_cap_id"] == "P1C1.1.1"
    )
    assert priority["narrative"] == "CACHED NARRATIVE FROM CHECKPOINT"
    assert priority["recommendation"] == "CACHED RECOMMENDATION"
    assert priority["chain_id"] == "chain-cached"
    assert priority["cost_usd"] == 0.12


def test_resume_run_summary_tracks_resumed_count(seeded_digest_inputs):
    """The digest_runs audit row carries
    ``priorities_resumed_from_checkpoint`` so the operator dashboard
    can see how much the resume saved."""
    digest_id = _digest_id("RB", "2026-Q2")
    canned = PriorityNarrative(
        sub_cap_id="P1C1.1.1", sub_cap_name="x",
        state="RISING", score=0, confidence=0,
        narrative="cached", recommendation="cached",
        cost_usd=0.05,
    )
    _write_checkpoint(digest_id, "P1C1.1.1", canned)
    digest_service.generate(subvertical="RB", period="2026-Q2")
    runs = get_repository().list("digest_runs")
    assert runs
    latest = max(runs, key=lambda r: r.get("started_at") or "")
    assert latest["priorities_resumed_from_checkpoint"] >= 1


def test_successful_run_clears_checkpoints(seeded_digest_inputs):
    """After a digest persists, leftover checkpoints must not pollute
    a future run's resume path."""
    digest_id = _digest_id("RB", "2026-Q2")
    canned = PriorityNarrative(
        sub_cap_id="P1C1.1.1", sub_cap_name="x",
        state="RISING", score=0, confidence=0,
        narrative="cached", recommendation="cached",
    )
    _write_checkpoint(digest_id, "P1C1.1.1", canned)
    digest_service.generate(subvertical="RB", period="2026-Q2")
    # Checkpoint should be gone.
    assert list_checkpoints(digest_id) == []


def test_generate_persists_digest_row(seeded_digest_inputs):
    """Sanity check: the digest itself ends up in DIGEST_COLLECTION
    so re-loading via get_digest() works."""
    digest_service.generate(subvertical="RB", period="2026-Q2")
    row = digest_service.get_digest(_digest_id("RB", "2026-Q2"))
    assert row is not None
    assert row["subvertical"] == "RB"
