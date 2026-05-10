"""RAG chat — vector retrieval + consultant loop wrapper."""

import pytest

from app.services import chat_service, news_service
from app.services.chat_service import _extract_subcap, _trim_history
from app.services.llm.router import reset_state_for_tests


@pytest.fixture
def seeded(settings_for_tests):
    from app.services import catalogue_service, sow_service
    catalogue_service.refresh_pillar("P1", by="test")
    sow_service.ingest_all()
    news_service.refresh()
    reset_state_for_tests()
    return settings_for_tests


def test_extract_subcap_finds_in_text():
    assert _extract_subcap("Tell me about P1C1.1.1 please") == "P1C1.1.1"
    assert _extract_subcap("no subcap here") is None


def test_trim_history_keeps_recent():
    turns = [{"role": "user", "text": f"t{i}"} for i in range(20)]
    out = _trim_history(turns)
    assert len(out) == 10
    assert out[-1]["text"] == "t19"


def test_post_message_returns_reply(seeded):
    reply = chat_service.post_message(message="What's the lifecycle of P1C1.1.1?")
    assert reply.conversation_id.startswith("chat-")
    assert reply.message_id.startswith("msg-")
    assert reply.reply
    assert isinstance(reply.citations, list)
    assert isinstance(reply.sources, list)


def test_post_message_persists_conversation(seeded):
    a = chat_service.post_message(message="First")
    b = chat_service.post_message(message="Follow-up", conversation_id=a.conversation_id)
    assert b.conversation_id == a.conversation_id
    convo = chat_service.get_conversation(a.conversation_id)
    assert convo is not None
    # 2 user + 2 assistant turns
    assert len(convo["turns"]) == 4


def test_list_conversations_orders_newest_first(seeded):
    a = chat_service.post_message(message="A")
    b = chat_service.post_message(message="B")
    convos = chat_service.list_conversations()
    assert convos[0]["conversation_id"] == b.conversation_id
    assert any(c["conversation_id"] == a.conversation_id for c in convos)
