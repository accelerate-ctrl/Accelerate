"""Client Journey synthesis + DMA handoff packet."""

import pytest

from app.services import (
    benchmarks_service,
    client_journey_service,
    lifecycle_service,
    news_service,
    vendor_intel_service,
)


@pytest.fixture
def seeded(settings_for_tests):
    from app.services import catalogue_service, sow_service, stories_service
    catalogue_service.refresh_pillar("P1", by="test")
    sow_service.ingest_all()
    stories_service.refresh_all()
    benchmarks_service.refresh(extrapolate=False)
    news_service.refresh()
    vendor_intel_service.refresh()
    lifecycle_service.recompute_all()
    return settings_for_tests


def test_journey_for_known_client(seeded):
    journey = client_journey_service.get_journey("Wells Fargo")
    assert journey is not None
    assert journey["client_name"] == "Wells Fargo"
    assert journey["sow_count_active"] >= 1
    assert journey["touched_subcaps"]
    # touched subcap rows should carry lifecycle state
    has_state = any(t.get("state") for t in journey["touched_subcaps"])
    assert has_state


def test_journey_404_for_unknown_client(seeded):
    journey = client_journey_service.get_journey("Imaginary Bank, N.A.")
    assert journey is None


def test_journey_collects_vendor_stack(seeded):
    journey = client_journey_service.get_journey("Wells Fargo")
    assert journey is not None
    assert journey["vendor_stack"]
    assert any(v["vendor"] == "Salesforce Financial Services Cloud" for v in journey["vendor_stack"])


def test_dma_packet_shape(seeded):
    packet = client_journey_service.dma_packet("Wells Fargo")
    assert packet is not None
    assert packet["schema_version"] == "dma-handoff-v1"
    assert packet["client"] == "Wells Fargo"
    assert "engagement" in packet
    assert "vendor_stack" in packet
    assert "priorities" in packet
    # active priorities filtered to RISING/STABLE/EMERGING only
    for p in packet["priorities"]:
        assert (p.get("state") or "").upper() in ("RISING", "STABLE", "EMERGING")


def test_refresh_all_builds_journey_per_client(seeded):
    out = client_journey_service.refresh_all()
    assert out["clients_built"] >= 2  # Wells Fargo + Northwestern Mutual etc
    persisted = client_journey_service.list_journeys()
    assert persisted
