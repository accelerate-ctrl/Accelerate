"""Vector store — local cosine search; Vertex Vector Search swap-in for prod.

Documents are persisted to ``vector_index`` in the repository with their
embedding vector.  ``search`` does a naive cosine over all documents in the
collection — fine for the volumes Batch 4 cares about (a few thousand SOW
chunks + a few hundred news / trends items).  When the catalogue grows,
the prod swap-in (`vertex_index.search`) keeps the same return shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..repository import get_repository
from .embeddings import embed_text

INDEX_COLLECTION = "vector_index"


@dataclass
class VectorHit:
    doc_id: str
    score: float
    text: str
    metadata: dict


class VectorStore:
    def upsert(self, doc_id: str, text: str, metadata: dict | None = None) -> None:
        repo = get_repository()
        repo.upsert(
            INDEX_COLLECTION,
            doc_id,
            {
                "doc_id": doc_id,
                "text": text,
                "embedding": embed_text(text),
                "metadata": metadata or {},
                "indexed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def upsert_many(self, items: list[tuple[str, str, dict | None]]) -> int:
        n = 0
        for doc_id, text, meta in items:
            self.upsert(doc_id, text, meta)
            n += 1
        return n

    def search(self, query: str, k: int = 5, filter_kind: str | None = None) -> list[VectorHit]:
        repo = get_repository()
        q = embed_text(query)
        hits: list[VectorHit] = []
        for rec in repo.list(INDEX_COLLECTION):
            if filter_kind and rec.get("metadata", {}).get("kind") != filter_kind:
                continue
            score = _cosine(q, rec["embedding"])
            hits.append(
                VectorHit(
                    doc_id=rec["doc_id"],
                    score=score,
                    text=rec["text"],
                    metadata=rec.get("metadata", {}),
                )
            )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]

    def size(self) -> int:
        return len(get_repository().list(INDEX_COLLECTION))

    def clear(self) -> None:
        repo = get_repository()
        for r in list(repo.list(INDEX_COLLECTION)):
            repo.delete(INDEX_COLLECTION, r["doc_id"])


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (na * nb)
