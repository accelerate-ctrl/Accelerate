"""Embeddings service.

Live mode: Vertex ``text-embedding-005`` via the Cloud AI Platform SDK.
Dev mode: a deterministic 256-dim hash-based embedding so vector search +
RAG still work end-to-end without any cloud calls.

The hash embedding is *not* semantic, but it is reproducible and lets the
unit tests assert exact-match retrieval for canned fixtures.  Once Vertex
creds are set, the live path takes over with no consumer changes.
"""

from __future__ import annotations

import hashlib
from typing import Sequence

from ...config import get_settings

DIMS = 256


def _hash_embed(text: str) -> list[float]:
    """SHA-512 → 8 floats per byte → normalize to unit length.

    Two identical strings produce the same vector; small edits produce a
    very different vector — fine for exact-match dev semantics.
    """
    digest = hashlib.sha512(text.encode("utf-8")).digest()
    # repeat digest until we have DIMS bytes
    raw = (digest * (DIMS // len(digest) + 1))[:DIMS]
    vals = [(b - 128) / 128.0 for b in raw]
    norm = sum(v * v for v in vals) ** 0.5 or 1.0
    return [v / norm for v in vals]


def embed_text(text: str) -> list[float]:
    s = get_settings()
    if not s.llm_live_mode:
        return _hash_embed(text)
    # Live Vertex path — lazy import so dev never needs the SDK.
    from vertexai.language_models import TextEmbeddingModel  # type: ignore[import-not-found]
    import vertexai  # type: ignore[import-not-found]

    if not s.gcp_project_id:
        raise RuntimeError("gcp_project_id not set; cannot call Vertex embeddings")
    vertexai.init(project=s.gcp_project_id, location=s.vertex_region)
    model = TextEmbeddingModel.from_pretrained(s.vertex_embedding_model)
    out = model.get_embeddings([text])
    return list(out[0].values)


def embed_batch(texts: Sequence[str]) -> list[list[float]]:
    return [embed_text(t) for t in texts]
