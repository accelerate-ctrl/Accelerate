from app.services.llm.embeddings import embed_text
from app.services.llm.vector_store import VectorStore


def test_embeddings_deterministic():
    a = embed_text("digital strategy document banking")
    b = embed_text("digital strategy document banking")
    assert a == b
    assert len(a) == 256


def test_search_returns_exact_match_top(settings_for_tests):
    vs = VectorStore()
    vs.upsert("doc-A", "wells fargo digital strategy retail banking", {"kind": "news"})
    vs.upsert("doc-B", "compliance regulatory change management framework", {"kind": "news"})
    hits = vs.search("wells fargo digital strategy retail banking", k=2)
    assert hits[0].doc_id == "doc-A"
    assert hits[0].score >= hits[1].score


def test_filter_by_kind(settings_for_tests):
    vs = VectorStore()
    vs.upsert("doc-A", "x", {"kind": "news"})
    vs.upsert("doc-B", "x", {"kind": "trend"})
    hits = vs.search("x", k=5, filter_kind="trend")
    assert all(h.metadata.get("kind") == "trend" for h in hits)
