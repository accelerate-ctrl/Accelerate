"""Persona-overlaid views."""

import pytest

from app.services import lifecycle_service, personas_service


@pytest.fixture
def seeded(settings_for_tests):
    from app.services import catalogue_service
    catalogue_service.refresh_pillar("P1", by="test")
    lifecycle_service.recompute_all()
    return settings_for_tests


def test_list_personas_aggregates(seeded):
    rows = personas_service.list_personas()
    assert rows
    # CIO appears on multiple subcaps in the Pillar 1 file
    cio = next((r for r in rows if r["name"] == "CIO"), None)
    assert cio is not None
    assert cio["subcap_count"] >= 1
    assert isinstance(cio["sample_subcaps"], list)


def test_get_persona_view_returns_subcaps(seeded):
    rows = personas_service.list_personas()
    name = rows[0]["name"]
    detail = personas_service.get_persona_view(name)
    assert detail is not None
    assert detail["persona"] == name
    assert detail["subcap_count"] > 0
    assert detail["subcaps"]
    # Per-subcap row carries lifecycle state
    assert all("state" in r for r in detail["subcaps"])


def test_get_persona_view_404(seeded):
    detail = personas_service.get_persona_view("NonExistentPersona")
    assert detail is None
