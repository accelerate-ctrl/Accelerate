"""Storage abstraction.

Two implementations share one interface:
  - InMemoryRepository: dict-of-lists, optionally JSON-persisted to disk for
    local dev / pytest.
  - MongoRepository: pymongo client backed by Firestore in MongoDB-compatibility
    mode (or vanilla MongoDB for emulator-less local runs).

Choice is driven by `Settings.use_gcp` and `Settings.firestore_mongo_uri`.

Keep this layer stupid-simple: collection-level CRUD + a couple of bulk
upserts. Domain logic lives in the services that compose it.
"""
from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol


class Repository(Protocol):
    def list(self, collection: str, filter: dict | None = None) -> list[dict]: ...
    def get(self, collection: str, doc_id: str) -> dict | None: ...
    def upsert(self, collection: str, doc_id: str, doc: dict) -> None: ...
    def upsert_many(self, collection: str, docs: list[tuple[str, dict]]) -> int: ...
    def delete(self, collection: str, doc_id: str) -> bool: ...
    def replace_collection(self, collection: str, docs: list[tuple[str, dict]]) -> int: ...
    def count(self, collection: str, filter: dict | None = None) -> int: ...
    def distinct(self, collection: str, field: str, filter: dict | None = None) -> list[Any]: ...


# ─── In-memory implementation ────────────────────────────────────────────────


class InMemoryRepository:
    """Thread-safe in-memory store. Optional JSON persistence."""

    def __init__(self, persist_path: str | None = None) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, dict[str, dict]] = {}
        self._persist_path = Path(persist_path) if persist_path else None
        # When >0 we batch _persist() calls instead of writing on every
        # mutation. Services with hot-loop upserts wrap them in
        # ``with repo.defer_persist():`` to avoid O(N²) disk writes.
        self._defer_depth = 0
        self._dirty = False
        if self._persist_path and self._persist_path.exists():
            try:
                self._data = json.loads(self._persist_path.read_text())
            except Exception:
                # corrupt cache → start fresh
                self._data = {}

    # public API ----------------------------------------------------------
    def list(self, collection: str, filter: dict | None = None) -> list[dict]:
        with self._lock:
            docs = list(self._data.get(collection, {}).values())
        return [deepcopy(d) for d in docs if _match(d, filter)]

    def get(self, collection: str, doc_id: str) -> dict | None:
        with self._lock:
            d = self._data.get(collection, {}).get(doc_id)
            return deepcopy(d) if d is not None else None

    def upsert(self, collection: str, doc_id: str, doc: dict) -> None:
        with self._lock:
            self._data.setdefault(collection, {})[doc_id] = deepcopy(doc)
        self._persist()

    def upsert_many(self, collection: str, docs: list[tuple[str, dict]]) -> int:
        with self._lock:
            target = self._data.setdefault(collection, {})
            for doc_id, doc in docs:
                target[doc_id] = deepcopy(doc)
        self._persist()
        return len(docs)

    def delete(self, collection: str, doc_id: str) -> bool:
        with self._lock:
            removed = self._data.get(collection, {}).pop(doc_id, None) is not None
        if removed:
            self._persist()
        return removed

    def replace_collection(self, collection: str, docs: list[tuple[str, dict]]) -> int:
        """Atomic-ish: drop & repopulate."""
        with self._lock:
            self._data[collection] = {doc_id: deepcopy(doc) for doc_id, doc in docs}
        self._persist()
        return len(docs)

    def count(self, collection: str, filter: dict | None = None) -> int:
        with self._lock:
            return sum(1 for d in self._data.get(collection, {}).values() if _match(d, filter))

    def distinct(self, collection: str, field: str, filter: dict | None = None) -> list[Any]:
        seen: set = set()
        with self._lock:
            for d in self._data.get(collection, {}).values():
                if not _match(d, filter):
                    continue
                v = d.get(field)
                if v is not None:
                    seen.add(v if not isinstance(v, list) else tuple(v))
        return sorted(seen, key=lambda x: str(x))

    # bulk-write helpers --------------------------------------------------
    @contextmanager
    def defer_persist(self):
        """Suspend disk writes for the duration of the block.

        On exit (when defer depth drops to 0) we flush once.  Nested calls
        compose; the inner blocks become no-ops.  Used by services that
        upsert thousands of rows in a tight loop (catalogue, stories,
        benchmarks, lifecycle).
        """
        with self._lock:
            self._defer_depth += 1
        try:
            yield
        finally:
            with self._lock:
                self._defer_depth -= 1
                should_flush = self._defer_depth == 0 and self._dirty
            if should_flush:
                self._flush_to_disk()

    # internals -----------------------------------------------------------
    def _persist(self) -> None:
        # Mark dirty + flush only if we're not inside a defer_persist block.
        if not self._persist_path:
            return
        with self._lock:
            self._dirty = True
            if self._defer_depth > 0:
                return
        self._flush_to_disk()

    def _flush_to_disk(self) -> None:
        if not self._persist_path:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                snapshot = json.dumps(self._data, default=str)
                self._dirty = False
            self._persist_path.write_text(snapshot)
        except Exception:
            pass


def _match(doc: dict, filter: dict | None) -> bool:
    """Tiny field-equality matcher; supports lists via 'in' semantics."""
    if not filter:
        return True
    for k, v in filter.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


# ─── Mongo (Firestore-MongoDB compat) implementation ─────────────────────────


class MongoRepository:
    """Pymongo-backed repository. Used when use_gcp=true.

    Works against:
      - Firestore in MongoDB-compatibility mode (production)
      - vanilla MongoDB (optional local-emulator-free dev mode)
    """

    def __init__(self, mongo_uri: str, db_name: str) -> None:
        from pymongo import MongoClient
        self._client = MongoClient(mongo_uri)
        self._db = self._client[db_name]

    def _coll(self, collection: str):
        return self._db[collection]

    @contextmanager
    def defer_persist(self):
        """No-op for Mongo — every write goes straight to Firestore."""
        yield

    def list(self, collection: str, filter: dict | None = None) -> list[dict]:
        return [_strip_mongo_id(d) for d in self._coll(collection).find(filter or {})]

    def get(self, collection: str, doc_id: str) -> dict | None:
        d = self._coll(collection).find_one({"_id": doc_id})
        return _strip_mongo_id(d) if d else None

    def upsert(self, collection: str, doc_id: str, doc: dict) -> None:
        payload = dict(doc)
        payload["_id"] = doc_id
        self._coll(collection).replace_one({"_id": doc_id}, payload, upsert=True)

    def upsert_many(self, collection: str, docs: list[tuple[str, dict]]) -> int:
        from pymongo import ReplaceOne
        ops = [
            ReplaceOne({"_id": doc_id}, {**doc, "_id": doc_id}, upsert=True)
            for doc_id, doc in docs
        ]
        if not ops:
            return 0
        result = self._coll(collection).bulk_write(ops, ordered=False)
        return result.upserted_count + result.modified_count

    def delete(self, collection: str, doc_id: str) -> bool:
        return self._coll(collection).delete_one({"_id": doc_id}).deleted_count > 0

    def replace_collection(self, collection: str, docs: list[tuple[str, dict]]) -> int:
        # Firestore-Mongo doesn't allow drop in some configurations; do a
        # delete-then-bulk-upsert. Single-thread inside this method.
        coll = self._coll(collection)
        coll.delete_many({})
        return self.upsert_many(collection, docs)

    def count(self, collection: str, filter: dict | None = None) -> int:
        return self._coll(collection).count_documents(filter or {})

    def distinct(self, collection: str, field: str, filter: dict | None = None) -> list[Any]:
        return list(self._coll(collection).distinct(field, filter or {}))


def _strip_mongo_id(d: dict | None) -> dict | None:
    if d is None:
        return None
    if "_id" in d:
        d = dict(d)
        d.pop("_id", None)
    return d


# ─── Provider ────────────────────────────────────────────────────────────────


_singleton: Repository | None = None


def get_repository() -> Repository:
    global _singleton
    if _singleton is not None:
        return _singleton
    from ..config import get_settings
    s = get_settings()
    if s.use_gcp and s.firestore_mongo_uri:
        _singleton = MongoRepository(
            mongo_uri=s.firestore_mongo_uri,
            db_name=s.firestore_mongo_db_name or s.firestore_database_id,
        )
    else:
        _singleton = InMemoryRepository(persist_path=s.local_repository_path)
    return _singleton


def reset_repository_for_tests() -> None:
    global _singleton
    _singleton = None
