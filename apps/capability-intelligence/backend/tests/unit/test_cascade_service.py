"""Cascade service tests (PRD FR-2, App Flow J4)."""

import pytest

from app.services import cascade_service
from app.services.catalogue_service import COLLECTIONS
from app.services.repository import get_repository


@pytest.fixture
def seeded_cascade(settings_for_tests):
    """Seed a small synthetic catalogue slice so the cascade has work
    to do without depending on a full pillar ingest."""
    repo = get_repository()
    sub_cap_id = "P1C1.1.1"
    repo.upsert(COLLECTIONS["subcaps"], sub_cap_id, {
        "sub_cap_id": sub_cap_id,
        "sub_cap_name": "Test Subcap",
        "pillar_id": "P1",
        "category_id": "C1",
        "l1_capability": "L1",
        "zennify_status": "Active",
    })
    # 3 stories
    for i in range(3):
        key = f"P1C1.1.1.S{i+1}"
        repo.upsert(COLLECTIONS["stories"], key, {
            "story_key": key,
            "sub_cap_id": sub_cap_id,
            "title": f"Story {i+1}",
        })
    # 2 L4 features
    for i in range(2):
        doc_id = f"{sub_cap_id}__L3PLAT__feature{i}"
        repo.upsert(COLLECTIONS["l4"], doc_id, {
            "sub_cap_id": sub_cap_id,
            "l3_platform_id": "L3PLAT",
            "feature_name": f"feature{i}",
        })
    # 1 maturity descriptor
    repo.upsert(COLLECTIONS["maturity"], sub_cap_id, {
        "sub_cap_id": sub_cap_id,
        "m1": "Foundational",
    })
    # 1 theme mapping
    repo.upsert(COLLECTIONS["themes"], f"AI::{sub_cap_id}", {
        "theme_name": "AI",
        "sub_cap_id": sub_cap_id,
    })
    return sub_cap_id


def test_preview_enumerates_downstream_rows(seeded_cascade):
    report = cascade_service.preview(seeded_cascade)
    assert report.sub_cap_id == seeded_cascade
    assert report.applied is False
    assert report.from_status == "Active"
    assert report.to_status == "Inactive"
    # 3 stories + 2 l4 + 1 maturity + 1 theme = 7
    assert report.total_rows_affected == 7
    labels = {t.label for t in report.targets}
    assert "User stories" in labels
    assert "L4 features" in labels
    assert "Maturity descriptors" in labels
    assert "Theme mappings" in labels


def test_preview_does_not_mutate(seeded_cascade):
    """Preview must be read-only: nothing changes."""
    cascade_service.preview(seeded_cascade)
    repo = get_repository()
    sub = repo.get(COLLECTIONS["subcaps"], seeded_cascade)
    assert sub["zennify_status"] == "Active"
    assert "cascade_status" not in sub


def test_preview_unknown_subcap_raises(settings_for_tests):
    with pytest.raises(KeyError):
        cascade_service.preview("DOES.NOT.EXIST")


def test_apply_requires_reason(seeded_cascade):
    with pytest.raises(ValueError):
        cascade_service.apply(seeded_cascade, reason="")


def test_apply_toggles_subcap_and_cascades(seeded_cascade):
    report = cascade_service.apply(
        seeded_cascade,
        to_status="Inactive",
        reason="Test deactivation",
        by="tester",
    )
    assert report.applied is True
    assert report.to_status == "Inactive"
    assert report.reason == "Test deactivation"
    # All 7 downstream rows + 1 subcap stamped with cascade_status=Inactive
    repo = get_repository()
    sub = repo.get(COLLECTIONS["subcaps"], seeded_cascade)
    assert sub["zennify_status"] == "Inactive"
    assert sub["cascade_status"] == "Inactive"
    stories = repo.list(COLLECTIONS["stories"], {"sub_cap_id": seeded_cascade})
    assert len(stories) == 3
    assert all(s["cascade_status"] == "Inactive" for s in stories)
    l4 = repo.list(COLLECTIONS["l4"], {"sub_cap_id": seeded_cascade})
    assert all(f["cascade_status"] == "Inactive" for f in l4)


def test_apply_logs_run(seeded_cascade):
    cascade_service.apply(
        seeded_cascade,
        to_status="Inactive",
        reason="Audit-fix test",
    )
    runs = cascade_service.list_runs()
    assert len(runs) >= 1
    latest = runs[0]
    assert latest["sub_cap_id"] == seeded_cascade
    assert latest["reason"] == "Audit-fix test"
    assert latest["total_rows_affected"] == 7


def test_apply_preserves_unrelated_rows(seeded_cascade):
    """Cascade must not touch rows for other subcaps."""
    repo = get_repository()
    other_subcap = "P1C1.1.2"
    repo.upsert(COLLECTIONS["subcaps"], other_subcap, {
        "sub_cap_id": other_subcap,
        "sub_cap_name": "Untouched",
        "zennify_status": "Active",
    })
    repo.upsert(COLLECTIONS["stories"], f"{other_subcap}.S1", {
        "story_key": f"{other_subcap}.S1",
        "sub_cap_id": other_subcap,
    })
    cascade_service.apply(seeded_cascade, reason="x")
    # Other subcap and its story remain untouched.
    untouched_sub = repo.get(COLLECTIONS["subcaps"], other_subcap)
    assert untouched_sub.get("cascade_status") is None
    assert untouched_sub["zennify_status"] == "Active"
    untouched_story = repo.get(COLLECTIONS["stories"], f"{other_subcap}.S1")
    assert untouched_story.get("cascade_status") is None


def test_apply_to_reactivate(seeded_cascade):
    """Reactivation is the inverse cascade — same machinery, different
    target status. Pillar leads sometimes need to roll back a toggle.
    """
    cascade_service.apply(seeded_cascade, to_status="Inactive", reason="off")
    report = cascade_service.apply(seeded_cascade, to_status="Active", reason="on")
    assert report.applied is True
    assert report.to_status == "Active"
    repo = get_repository()
    stories = repo.list(COLLECTIONS["stories"], {"sub_cap_id": seeded_cascade})
    assert all(s["cascade_status"] == "Active" for s in stories)


def test_preview_includes_sample_ids(seeded_cascade):
    report = cascade_service.preview(seeded_cascade)
    for t in report.targets:
        assert len(t.sample_ids) > 0
        assert all(isinstance(s, str) for s in t.sample_ids)
