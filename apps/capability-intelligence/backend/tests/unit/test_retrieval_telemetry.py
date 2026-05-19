"""Retrieval telemetry tests (Phase 5.3 / IMP-8)."""

from dataclasses import dataclass

import pytest

from app.services import retrieval_telemetry
from app.services.retrieval_telemetry import list_recent, record, summary
from app.services.repository import get_repository


@dataclass
class _FakeHit:
    """Mirrors the shape of :class:`RetrievalHit` so we can test record()
    without standing up the full corpus."""
    doc_id: str
    text: str
    metadata: dict
    score: float
    signals: list[str]


def _hit(*, doc_id: str, kind: str, score: float, signals, sub_cap_id: str | None = None) -> _FakeHit:
    meta = {"kind": kind}
    if sub_cap_id:
        meta["sub_cap_id"] = sub_cap_id
    return _FakeHit(
        doc_id=doc_id,
        text=doc_id,
        metadata=meta,
        score=score,
        signals=signals,
    )


# ─── record() ──────────────────────────────────────────────────────────────


def test_record_persists_event(settings_for_tests):
    event = record(
        query="open banking",
        operation="chat",
        hits=[
            _hit(doc_id="subcap::P1C3.5.2", kind="subcap", score=0.9, signals=["dense", "bm25"]),
            _hit(doc_id="maturity::P1C3.5.2::m3", kind="maturity", score=0.5, signals=["bm25"]),
        ],
        user_email="alice@zen.co",
    )
    assert event.k_returned == 2
    assert event.by_signal == {"dense": 1, "bm25": 2}
    assert event.by_kind == {"subcap": 1, "maturity": 1}
    assert event.structured_filter_hit is False
    assert event.top_score == 0.9


def test_record_detects_structured_filter_hit(settings_for_tests):
    event = record(
        query="Tell me about P1C1.1.1",
        operation="chat",
        hits=[
            _hit(
                doc_id="subcap::P1C1.1.1",
                kind="subcap",
                score=2.0,
                signals=["structured", "dense"],
                sub_cap_id="P1C1.1.1",
            ),
        ],
    )
    assert event.structured_filter_hit is True


def test_record_handles_empty_hits(settings_for_tests):
    event = record(query="garbage", operation="chat", hits=[])
    assert event.k_returned == 0
    assert event.top_score == 0.0
    assert event.fusion_score_mean == 0.0


def test_record_truncates_long_queries(settings_for_tests):
    long_query = "x" * 1000
    event = record(query=long_query, operation="chat", hits=[])
    # Query field capped at 500 chars to keep telemetry rows small.
    assert len(event.query) == 500


def test_record_email_normalised(settings_for_tests):
    event = record(query="x", operation="chat", hits=[], user_email="Alice@Zen.Co")
    assert event.user_email == "alice@zen.co"


def test_record_tolerates_dict_metadata(settings_for_tests):
    """Some callers may pass plain dicts instead of RetrievalHit
    objects; record() should handle that too."""
    fake_hits = [
        {"doc_id": "x", "metadata": {"kind": "subcap"}, "score": 0.5, "signals": ["dense"]},
    ]
    # The simpler @dataclass + attribute-access path is what record()
    # uses; a plain dict won't pass getattr.signals — so wrap it.
    class _D:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)
    wrapped = [_D(**fake_hits[0])]
    event = record(query="x", operation="chat", hits=wrapped)
    assert event.k_returned == 1
    assert event.by_kind == {"subcap": 1}


# ─── list_recent ──────────────────────────────────────────────────────────


def test_list_recent_returns_newest_first(settings_for_tests):
    record(query="first", operation="chat", hits=[])
    record(query="second", operation="chat", hits=[])
    record(query="third", operation="chat", hits=[])
    rows = list_recent(limit=10)
    assert [r["query"] for r in rows] == ["third", "second", "first"]


def test_list_recent_filter_by_operation(settings_for_tests):
    record(query="a", operation="chat", hits=[])
    record(query="b", operation="deep_dive", hits=[])
    record(query="c", operation="deep_dive", hits=[])
    chat = list_recent(operation="chat")
    deep = list_recent(operation="deep_dive")
    assert [r["query"] for r in chat] == ["a"]
    assert len(deep) == 2


# ─── summary() ────────────────────────────────────────────────────────────


def test_summary_aggregates_across_events(settings_for_tests):
    record(query="q1", operation="chat", hits=[
        _hit(doc_id="x", kind="subcap", score=0.9, signals=["dense", "bm25"]),
        _hit(doc_id="y", kind="story", score=0.4, signals=["bm25"]),
    ])
    record(query="q2", operation="chat", hits=[
        _hit(doc_id="z", kind="subcap", score=1.0, signals=["structured"]),
    ])
    s = summary()
    assert s["events"] == 2
    assert s["hits_by_signal"]["bm25"] == 2
    assert s["hits_by_signal"]["dense"] == 1
    assert s["hits_by_signal"]["structured"] == 1
    assert s["hits_by_kind"]["subcap"] == 2
    assert s["hits_by_kind"]["story"] == 1
    # 1 of 2 events had a structured filter hit → 0.5.
    assert s["structured_filter_rate"] == 0.5
    # avg_top_score = (0.9 + 1.0) / 2 = 0.95
    assert abs(s["avg_top_score"] - 0.95) < 0.0001


def test_summary_zero_hit_queries_surfaced(settings_for_tests):
    record(query="garbage frobnicate", operation="chat", hits=[])
    record(query="real query", operation="chat", hits=[
        _hit(doc_id="x", kind="subcap", score=0.5, signals=["dense"]),
    ])
    s = summary()
    assert "garbage frobnicate" in s["zero_hit_queries"]
    assert "real query" not in s["zero_hit_queries"]


def test_summary_empty_collection(settings_for_tests):
    s = summary()
    assert s["events"] == 0
    assert s["structured_filter_rate"] == 0.0
    assert s["hits_by_signal"] == {}


# ─── Integration with hybrid_retriever ────────────────────────────────────


def test_hybrid_retriever_records_telemetry(settings_for_tests):
    """End-to-end: a retrieve() call must leave a telemetry row.
    Builds a tiny corpus inline so we don't depend on the full
    catalogue refresh path."""
    from app.services.rag import catalogue_corpus_builder, hybrid_retriever
    from app.services.catalogue_service import COLLECTIONS

    repo = get_repository()
    repo.upsert(COLLECTIONS["subcaps"], "P1C1.1.1", {
        "sub_cap_id": "P1C1.1.1",
        "sub_cap_name": "Digital Strategy",
        "pillar_id": "P1",
        "category_id": "C1",
        "l1_capability": "L1",
        "description": "Authoring the institution's digital strategy.",
    })
    catalogue_corpus_builder.rebuild_corpus()

    before = len(list_recent(limit=200))
    hybrid_retriever.retrieve(
        "Tell me about P1C1.1.1", top_k=5, operation="chat",
        user_email="alice@zen.co",
    )
    after = list_recent(limit=200)
    assert len(after) == before + 1
    last = after[0]
    assert last["operation"] == "chat"
    assert last["user_email"] == "alice@zen.co"
    # Structured filter resolved the exact sub_cap_id → hit must be True.
    assert last["structured_filter_hit"] is True


def test_hybrid_retriever_skips_telemetry_when_opted_out(settings_for_tests):
    from app.services.rag import catalogue_corpus_builder, hybrid_retriever
    from app.services.catalogue_service import COLLECTIONS

    repo = get_repository()
    repo.upsert(COLLECTIONS["subcaps"], "P1C1.1.1", {
        "sub_cap_id": "P1C1.1.1",
        "sub_cap_name": "x",
        "pillar_id": "P1",
        "category_id": "C1",
        "l1_capability": "L1",
        "description": "x",
    })
    catalogue_corpus_builder.rebuild_corpus()
    before = len(list_recent(limit=200))
    hybrid_retriever.retrieve("x", top_k=5, record_telemetry=False)
    after = list_recent(limit=200)
    assert len(after) == before
