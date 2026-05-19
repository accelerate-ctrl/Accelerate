"""IMP-17 — DMA handoff contract tests.

The same test module ships in both repos (this one and the DMA App). The
fixture and validator are the contract; if either repo's CI fails, the
producer and consumer have drifted.
"""

from __future__ import annotations

import copy

import pytest

from app.services.dma_handoff import contract as dma


def _fixture():
    return copy.deepcopy(dma.DMA_HANDOFF_FIXTURE)


def test_fixture_passes_validator():
    dma.validate_dma_packet(_fixture())


def test_missing_required_top_level_field_raises():
    packet = _fixture()
    del packet["client"]
    with pytest.raises(dma.ContractError) as exc:
        dma.validate_dma_packet(packet)
    assert "client" in str(exc.value)


def test_wrong_schema_version_raises():
    packet = _fixture()
    packet["schema_version"] = "dma-handoff-v99"
    with pytest.raises(dma.ContractError) as exc:
        dma.validate_dma_packet(packet)
    assert "schema_version" in str(exc.value)


def test_engagement_negative_count_rejected():
    packet = _fixture()
    packet["engagement"]["active"] = -1
    with pytest.raises(dma.ContractError) as exc:
        dma.validate_dma_packet(packet)
    assert "engagement.active" in str(exc.value)


def test_engagement_missing_subfield_rejected():
    packet = _fixture()
    del packet["engagement"]["archived"]
    with pytest.raises(dma.ContractError) as exc:
        dma.validate_dma_packet(packet)
    assert "engagement" in str(exc.value) and "archived" in str(exc.value)


def test_priorities_capped_at_ten():
    packet = _fixture()
    prio = packet["priorities"][0]
    packet["priorities"] = [prio for _ in range(11)]
    with pytest.raises(dma.ContractError) as exc:
        dma.validate_dma_packet(packet)
    assert "priorities" in str(exc.value)


def test_priority_score_out_of_range_rejected():
    packet = _fixture()
    packet["priorities"][0]["score"] = 1.5
    with pytest.raises(dma.ContractError) as exc:
        dma.validate_dma_packet(packet)
    assert "score" in str(exc.value)


def test_priority_state_unknown_rejected():
    packet = _fixture()
    packet["priorities"][0]["state"] = "BANANA"
    with pytest.raises(dma.ContractError) as exc:
        dma.validate_dma_packet(packet)
    assert "state" in str(exc.value)


def test_priority_state_market_signal_vocab_accepted():
    # Phase 1 introduced market-signal vocab — both legacy and new states
    # must validate during the transition window.
    packet = _fixture()
    packet["priorities"][0]["state"] = "emerging"
    dma.validate_dma_packet(packet)


def test_vendor_confidence_out_of_range_rejected():
    packet = _fixture()
    packet["vendor_stack"][0]["confidence"] = 2.0
    with pytest.raises(dma.ContractError) as exc:
        dma.validate_dma_packet(packet)
    assert "confidence" in str(exc.value)


def test_empty_subverticals_allowed():
    # DMA tolerates an empty subvertical list — some clients have SOWs
    # that don't carry the subvertical tag yet.
    packet = _fixture()
    packet["subverticals"] = []
    dma.validate_dma_packet(packet)


def test_non_list_subverticals_rejected():
    packet = _fixture()
    packet["subverticals"] = "retail-banking"  # type: ignore[assignment]
    with pytest.raises(dma.ContractError):
        dma.validate_dma_packet(packet)


def test_non_dict_packet_raises():
    with pytest.raises(dma.ContractError):
        dma.validate_dma_packet([])  # type: ignore[arg-type]


def test_priority_not_dict_rejected():
    packet = _fixture()
    packet["priorities"] = ["not-a-dict"]
    with pytest.raises(dma.ContractError):
        dma.validate_dma_packet(packet)


def test_bool_in_int_field_rejected():
    # bool is a subclass of int — but boolean engagement counts almost
    # always indicate a serialisation bug.
    packet = _fixture()
    packet["engagement"]["active"] = True
    with pytest.raises(dma.ContractError) as exc:
        dma.validate_dma_packet(packet)
    assert "active" in str(exc.value)


def test_optional_asset_size_can_be_none():
    packet = _fixture()
    packet["asset_size_usd_bn"] = None
    dma.validate_dma_packet(packet)


def test_optional_asset_size_can_be_omitted():
    packet = _fixture()
    del packet["asset_size_usd_bn"]
    dma.validate_dma_packet(packet)


def test_live_dma_packet_emitter_satisfies_contract(settings_for_tests):
    # Producer/consumer integration: call the real emitter and validate.
    from app.services import catalogue_service, client_journey_service, sow_service
    catalogue_service.refresh_pillar("P1", by="test")
    sow_service.ingest_all()
    repo = client_journey_service.get_repository()
    clients = sorted({s.get("client_name") for s in repo.list("sows") if s.get("client_name")})
    assert clients, "fixture sows must seed at least one client"
    for client in clients[:3]:  # don't validate 100 — first few is enough
        packet = client_journey_service.dma_packet(client)
        if packet is None:
            continue
        dma.validate_dma_packet(packet)
