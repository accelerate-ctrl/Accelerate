"""Hybrid retriever for catalogue-grounded RAG (PRD FR-16).

Three retrieval signals merged via reciprocal-rank fusion (RRF):

1. **Structured filter** — when the query mentions a recognisable
   identifier (sub_cap_id, story key, L3 platform id), pull the exact
   row first and rank it #1 with a high RRF boost.
2. **Dense semantic** — vector cosine over the embedded chunks (uses
   the existing :class:`VectorStore`).
3. **BM25 keyword** — token-overlap scoring with TF-IDF-style weighting.
   Catches term matches (capability names, theme keywords) that dense
   embeddings sometimes miss when the query phrasing diverges from the
   chunk wording.

Each signal returns its own ranked list; reciprocal-rank fusion combines
them (``score = sum(1 / (k + rank))``) so a hit ranked #1 by *either*
signal still surfaces near the top of the fused list.

Returned shape: ``list[RetrievalHit]`` with score, kind, sub_cap_id (when
known), and the underlying text + metadata so downstream prompts have
everything they need to cite.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from ..llm.vector_store import VectorStore
from ..repository import get_repository

INDEX_COLLECTION = "vector_index"

# RRF constant — Wikipedia / Cormack et al. recommend k=60; smaller k
# weights top hits more heavily.
_RRF_K = 60


# ─── Identifier patterns the structured filter recognises ──────────────────


# Sub_Cap_ID per the v7.0 schema. Example: P1C2.3.1, P3C1.5.WM1.
_SUBCAP_RX = re.compile(r"\bP[1-4]C\d+\.[A-Za-z0-9]+\.[A-Za-z0-9]+\b")
# Story key. Example: P1C2.3.1.S5.
_STORY_RX = re.compile(r"\bP[1-4]C\d+\.[A-Za-z0-9]+\.[A-Za-z0-9]+\.S\d+\b")
# L3 platform id. Example: L3-SF-FSC, L3-DB-LAKEHOUSE.
_L3_RX = re.compile(r"\bL3-[A-Z]{2,}-[A-Z0-9-]+\b")


@dataclass
class RetrievalHit:
    """One row in the fused retrieval result.

    ``score`` is the post-RRF score (higher = better). ``signals`` lists
    which retrieval channels contributed, so the FE can render
    provenance chips (e.g., "dense + bm25").
    """

    doc_id: str
    text: str
    metadata: dict[str, Any]
    score: float
    signals: list[str]


# ─── Helpers ────────────────────────────────────────────────────────────────


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z0-9_]{3,}", text or "")]


def _bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    df: dict[str, int],
    n_docs: int,
    avgdl: float,
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """Compact BM25. No stemming; relies on the corpus already being
    lower-cased + minimal-stopworded."""
    if not doc_tokens:
        return 0.0
    tf = Counter(doc_tokens)
    doc_len = len(doc_tokens)
    score = 0.0
    for q in query_tokens:
        if q not in tf:
            continue
        idf = math.log(((n_docs - df.get(q, 0) + 0.5) / (df.get(q, 0) + 0.5)) + 1)
        f = tf[q]
        score += idf * ((f * (k1 + 1)) / (f + k1 * (1 - b + b * (doc_len / avgdl))))
    return score


def _structured_lookup(query: str) -> list[dict]:
    """Resolve exact identifiers in the query to catalogue rows.

    Returns rows wrapped in a vector-store-compatible shape so the
    downstream RRF merge sees a uniform record format.
    """
    repo = get_repository()
    out: list[dict] = []

    # Story keys are a strict subset of subcap-shaped ids; match them
    # first to avoid double-counting.
    for key in _STORY_RX.findall(query):
        story = repo.get("stories", key)
        if story:
            out.append({
                "doc_id": f"story::{key}",
                "text": f"{key}: {story.get('summary') or ''}",
                "metadata": {
                    "kind": "story",
                    "sub_cap_id": story.get("sub_cap_id"),
                    "title": key,
                    "source_id": key,
                },
            })

    for sid in _SUBCAP_RX.findall(query):
        # Skip if the same prefix already matched as a story key above.
        if any(o["metadata"].get("title") == sid for o in out):
            continue
        sub = repo.get("subcaps", sid)
        if sub:
            parts = [
                f"{sid} — {sub.get('sub_cap_name', '?')}",
                f"Pillar {sub.get('pillar_id', '?')}, L1 {sub.get('l1_capability', '?')}",
            ]
            if sub.get("description"):
                parts.append(str(sub["description"]))
            out.append({
                "doc_id": f"subcap::{sid}",
                "text": "\n".join(parts),
                "metadata": {
                    "kind": "subcap",
                    "sub_cap_id": sid,
                    "pillar_id": sub.get("pillar_id"),
                    "title": sub.get("sub_cap_name", sid),
                    "source_id": sid,
                },
            })

    for l3_id in _L3_RX.findall(query):
        l3 = repo.get("l3_platforms", l3_id)
        if l3:
            out.append({
                "doc_id": f"l3::{l3_id}",
                "text": f"{l3_id} {l3.get('name', '')}: {l3.get('description') or ''}",
                "metadata": {
                    "kind": "l3_platform",
                    "title": l3.get("name") or l3_id,
                    "source_id": l3_id,
                },
            })

    return out


def _load_catalogue_chunks() -> list[dict]:
    """All vector-index rows whose metadata.catalogue_version starts
    with ``corpus-`` (i.e. emitted by catalogue_corpus_builder).
    """
    repo = get_repository()
    return [
        r for r in repo.list(INDEX_COLLECTION)
        if str((r.get("metadata") or {}).get("catalogue_version", "")).startswith("corpus-")
    ]


def _bm25_search(query: str, chunks: list[dict], k: int) -> list[tuple[float, dict]]:
    """BM25 search over the catalogue chunks. Returns ``[(score, row)]``
    sorted by score DESC.
    """
    query_tokens = _tokenize(query)
    if not query_tokens or not chunks:
        return []
    # Pre-tokenize once.
    doc_token_lists = [_tokenize(c.get("text", "")) for c in chunks]
    df: dict[str, int] = Counter()
    for tokens in doc_token_lists:
        for term in set(tokens):
            df[term] += 1
    n_docs = len(chunks)
    avgdl = sum(len(t) for t in doc_token_lists) / max(1, n_docs)

    scored: list[tuple[float, dict]] = []
    for i, c in enumerate(chunks):
        s = _bm25_score(query_tokens, doc_token_lists[i], df, n_docs, avgdl)
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:k]


def _dense_search(query: str, k: int) -> list:
    """Wrap VectorStore.search but return raw rows in the same shape as
    the BM25 path so the RRF merge is uniform.
    """
    vs = VectorStore()
    if vs.size() == 0:
        return []
    return vs.search(query, k=k)


# ─── Public API ────────────────────────────────────────────────────────────


def retrieve(
    query: str,
    *,
    top_k: int = 12,
    candidates_per_signal: int = 20,
) -> list[RetrievalHit]:
    """Retrieve catalogue chunks matching the query via three signals
    merged with reciprocal-rank fusion.

    - ``top_k`` is the size of the returned list.
    - ``candidates_per_signal`` is how many hits each signal contributes
      before the fusion. Larger values trade compute for recall; 20 is
      a good default that keeps each query under 50ms on the in-memory
      repository at full v7.0 catalogue scale.
    """
    fused: dict[str, dict] = {}

    def _add(record: dict, *, rank: int, signal: str) -> None:
        doc_id = record["doc_id"]
        if doc_id not in fused:
            fused[doc_id] = {
                "doc_id": doc_id,
                "text": record["text"],
                "metadata": dict(record.get("metadata") or {}),
                "score": 0.0,
                "signals": [],
            }
        fused[doc_id]["score"] += 1.0 / (_RRF_K + rank)
        if signal not in fused[doc_id]["signals"]:
            fused[doc_id]["signals"].append(signal)

    # 1) Structured filter — exact-id hits get a strong RRF boost by
    #    being inserted at rank 1.
    for i, row in enumerate(_structured_lookup(query)):
        _add(row, rank=i + 1, signal="structured")

    # 2) Dense semantic.
    for i, hit in enumerate(_dense_search(query, candidates_per_signal)):
        _add(
            {
                "doc_id": hit.doc_id,
                "text": hit.text,
                "metadata": hit.metadata,
            },
            rank=i + 1,
            signal="dense",
        )

    # 3) BM25.
    chunks = _load_catalogue_chunks()
    for i, (_s, row) in enumerate(_bm25_search(query, chunks, candidates_per_signal)):
        _add(row, rank=i + 1, signal="bm25")

    hits = [
        RetrievalHit(
            doc_id=v["doc_id"],
            text=v["text"],
            metadata=v["metadata"],
            score=round(v["score"], 6),
            signals=v["signals"],
        )
        for v in fused.values()
    ]
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]


__all__ = ["RetrievalHit", "retrieve"]
