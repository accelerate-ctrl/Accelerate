"""LLM router + adapters + cache + cost tracker + embeddings + vector store.

The router exposes a single :func:`call` function that picks an adapter based
on the requested ``model`` enum.  In dev (``llm_live_mode=False``) every
adapter resolves to deterministic canned responses keyed off the prompt
hash so the entire consultant loop runs hermetically.

Public surface:

    router.call(LlmRequest) -> LlmResponse
    embeddings.embed_text(text) -> list[float]
    vector_store.search(query, k) -> list[VectorHit]
    cost_tracker.spend_today() -> float
"""

from .router import LlmRequest, LlmResponse, ModelKind, call  # noqa: F401
from .cache import LlmCache  # noqa: F401
from .cost_tracker import CostTracker, BudgetExceeded  # noqa: F401
from .embeddings import embed_text, embed_batch  # noqa: F401
from .vector_store import VectorHit, VectorStore  # noqa: F401
