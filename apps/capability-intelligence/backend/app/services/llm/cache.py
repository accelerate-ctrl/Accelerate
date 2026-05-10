"""Content-hash keyed LLM cache.

Backed by the Repository abstraction so it persists across uvicorn restarts
in dev (JSON file) and across pods in prod (Firestore-Mongo).  Eviction is
soft-LRU by ``hit_at`` with a ceiling of 5,000 entries by default.  Cache
is the *first* line of cost defense — typical loops re-issue the same
prompt many times.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ..repository import get_repository

if TYPE_CHECKING:
    from .router import LlmRequest, LlmResponse

CACHE_COLLECTION = "llm_cache"
DEFAULT_MAX_ENTRIES = 5000


def _cache_key(req: LlmRequest) -> str:
    payload = json.dumps(
        {
            "model": req.model.value,
            "system": req.system or "",
            "prompt": req.prompt,
            "temperature": round(req.temperature, 4),
            "max_tokens": req.max_tokens,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class LlmCache:
    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        self.max_entries = max_entries

    def get(self, req: LlmRequest) -> LlmResponse | None:
        from .router import LlmResponse, ModelKind  # late import to avoid cycle

        repo = get_repository()
        rec = repo.get(CACHE_COLLECTION, _cache_key(req))
        if not rec:
            return None
        # touch hit_at for LRU tracking
        rec = {**rec, "hit_at": datetime.now(timezone.utc).isoformat()}
        repo.upsert(CACHE_COLLECTION, rec["key"], rec)
        return LlmResponse(
            text=rec["text"],
            model=ModelKind(rec["model"]),
            cached=True,
            input_tokens=rec["input_tokens"],
            output_tokens=rec["output_tokens"],
            cost_usd=0.0,  # cached hits cost nothing
            finish_reason=rec.get("finish_reason", "stop"),
            raw={"adapter": "cache"},
        )

    def put(self, req: LlmRequest, resp: LlmResponse) -> None:
        repo = get_repository()
        now = datetime.now(timezone.utc).isoformat()
        key = _cache_key(req)
        rec = {
            "key": key,
            "model": resp.model.value,
            "text": resp.text,
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "finish_reason": resp.finish_reason,
            "stored_at": now,
            "hit_at": now,
        }
        repo.upsert(CACHE_COLLECTION, key, rec)
        self._evict_if_needed()

    def _evict_if_needed(self) -> None:
        repo = get_repository()
        entries = repo.list(CACHE_COLLECTION)
        if len(entries) <= self.max_entries:
            return
        entries.sort(key=lambda e: e.get("hit_at", ""))
        n_drop = max(1, len(entries) - self.max_entries + len(entries) // 10)
        for e in entries[:n_drop]:
            repo.delete(CACHE_COLLECTION, e["key"])

    def clear(self) -> None:
        repo = get_repository()
        for e in list(repo.list(CACHE_COLLECTION)):
            repo.delete(CACHE_COLLECTION, e["key"])

    def size(self) -> int:
        return len(get_repository().list(CACHE_COLLECTION))
