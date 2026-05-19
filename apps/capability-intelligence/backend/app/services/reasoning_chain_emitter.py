"""Lightweight reasoning-chain emitter for AI-output services (F02).

Background — QA_AUDIT F02 / Implementation Steps §2.2: today only
:mod:`consultant_loop` emits ``reasoning_chains/{chain_id}`` documents.
Every other AI-output service (news impact synthesis, vendor scan,
suggestion proposer, graph Layer-B proposer, digest synthesis) calls
an LLM and persists a result without recording *how* that result was
produced. The Subcap Deep Dive, AI Chat citation cards, and Reasoning
Chain Viewer all expect a chain id alongside every AI assertion — the
v1 trust surface depends on it.

This module ships a thin context-manager + decorator that any service
can wrap around its AI work. It does NOT replace the full 7-step
consultant loop (which has gates, adversarial, persistence into
suggestions, etc.). It produces a single ``reasoning_chains`` row with
steps + sources + output summary + claim labels + cost, so the trust
surface has a uniform chain to render no matter which service produced
the AI output.

Usage::

    from app.services.reasoning_chain_emitter import emit_chain

    with emit_chain(operation="news_impact",
                    sub_cap_id=item.get("id"),
                    leverage_tier="LOW") as chain:
        chain.step("retrieve",
                   input_summary="news item + 60-subcap inventory",
                   output_summary=f"{len(subcaps)} subcaps in scope")
        chain.step("llm",
                   model="gemini-flash",
                   input_summary="impact-classifier prompt",
                   output_summary=...)
        chain.attach_sources([{"id": item["id"], "url": item["url"], "tier": "T3"}])
        chain.attach_output({"summary": ..., "claims": [...]})

The chain is persisted on exit (unless the block raised, in which case
the chain is still persisted with ``overall=fail`` + the exception
class name in the failure step). This matters because failures are
exactly what we want to see in the audit dashboard.
"""

from __future__ import annotations

import logging
import traceback
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.models.common import schema_version

from .repository import get_repository

logger = logging.getLogger(__name__)

CHAIN_COLLECTION = "reasoning_chains"


@dataclass
class _ChainStep:
    name: str
    started_at: str
    completed_at: str
    model: str | None = None
    input_summary: str = ""
    output_summary: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    cached: bool = False
    detail: dict[str, Any] = field(default_factory=dict)


class ChainEmitter:
    """Per-operation reasoning-chain builder.

    Not thread-safe by design — each LLM operation should construct its
    own emitter. The emitter buffers steps in memory and persists once
    on ``commit()`` (called automatically by the :func:`emit_chain`
    context manager).
    """

    def __init__(
        self,
        *,
        operation: str,
        sub_cap_id: str | None = None,
        leverage_tier: str = "LOW",
        pillar_id: str | None = None,
        subvertical: str | None = None,
    ) -> None:
        self.chain_id = f"chain-{operation}-{uuid4().hex[:12]}"
        self.operation = operation
        self.sub_cap_id = sub_cap_id
        self.leverage_tier = leverage_tier
        self.pillar_id = pillar_id
        self.subvertical = subvertical
        self.started_at = datetime.now(timezone.utc)
        self.steps: list[_ChainStep] = []
        self.sources: list[dict] = []
        self.output: dict = {}
        self.failure: dict | None = None
        self._committed = False

    # ─── Building API ──────────────────────────────────────────────────

    def step(
        self,
        name: str,
        *,
        model: str | None = None,
        input_summary: str = "",
        output_summary: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        cached: bool = False,
        detail: dict | None = None,
    ) -> None:
        """Record one step. Caller is responsible for ordering."""
        now = datetime.now(timezone.utc).isoformat()
        self.steps.append(_ChainStep(
            name=name,
            started_at=now,
            completed_at=now,
            model=model,
            input_summary=input_summary[:400],
            output_summary=output_summary[:400],
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            cached=cached,
            detail=detail or {},
        ))

    def attach_sources(self, sources: list[dict]) -> None:
        """Replace the source list. Each entry should carry at minimum
        ``id`` and ``tier`` so the citation row can render. We accept
        whatever the service hands over; downstream code is permissive
        on missing keys.
        """
        self.sources = list(sources or [])

    def attach_output(self, output: dict) -> None:
        """Replace the output payload. Typically the service's
        synthesised result (impact dict, suggestion, edge proposal,
        etc.). Surfaced inline on the Reasoning Chain Viewer page.
        """
        self.output = dict(output or {})

    def record_failure(self, exc: BaseException) -> None:
        """Capture a failure for the audit trail without re-raising.

        The ``emit_chain`` context manager calls this automatically when
        the wrapped block raises; services that catch exceptions
        themselves can call it explicitly to log a soft-fail.
        """
        self.failure = {
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:400],
            "traceback": traceback.format_exc()[-1200:],
        }

    # ─── Persistence ───────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        completed = datetime.now(timezone.utc)
        total_cost = sum(s.cost_usd for s in self.steps)
        overall = "fail" if self.failure else "pass"
        return {
            "chain_id": self.chain_id,
            "operation": self.operation,
            "sub_cap_id": self.sub_cap_id,
            "pillar_id": self.pillar_id,
            "subvertical": self.subvertical,
            "leverage_tier": self.leverage_tier,
            "started_at": self.started_at.isoformat(),
            "completed_at": completed.isoformat(),
            "steps": [asdict(s) for s in self.steps],
            "sources": self.sources,
            "output": self.output,
            "overall": overall,
            "total_cost_usd": round(total_cost, 6),
            "failure": self.failure,
            "_schema_version": schema_version("reasoning_chain"),
        }

    def commit(self) -> dict[str, Any]:
        """Persist the chain to the repository. Idempotent — calling
        commit() twice on the same emitter is a no-op."""
        if self._committed:
            return self.to_dict()
        payload = self.to_dict()
        try:
            get_repository().upsert(CHAIN_COLLECTION, self.chain_id, payload)
        except Exception:
            # Persistence failure must NOT propagate — the AI work
            # already happened. Log loudly so observability picks it up.
            logger.exception("failed to persist reasoning chain %s", self.chain_id)
        self._committed = True
        return payload


@contextmanager
def emit_chain(
    *,
    operation: str,
    sub_cap_id: str | None = None,
    leverage_tier: str = "LOW",
    pillar_id: str | None = None,
    subvertical: str | None = None,
):
    """Context manager that yields a :class:`ChainEmitter` and commits
    it on exit. If the block raises, the failure is recorded on the
    chain before re-raising so the audit trail captures both success
    and crash paths.
    """
    emitter = ChainEmitter(
        operation=operation,
        sub_cap_id=sub_cap_id,
        leverage_tier=leverage_tier,
        pillar_id=pillar_id,
        subvertical=subvertical,
    )
    try:
        yield emitter
    except Exception as exc:
        emitter.record_failure(exc)
        emitter.commit()
        raise
    emitter.commit()


def list_chains(
    *,
    operation: str | None = None,
    sub_cap_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Recent chains, newest first. Used by the Reasoning Chain Viewer
    and the Subcap Deep Dive recent-chains widget.
    """
    rows = get_repository().list(CHAIN_COLLECTION)
    if operation:
        rows = [r for r in rows if r.get("operation") == operation]
    if sub_cap_id:
        rows = [r for r in rows if r.get("sub_cap_id") == sub_cap_id]
    rows.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    return rows[:limit]


__all__ = [
    "CHAIN_COLLECTION",
    "ChainEmitter",
    "emit_chain",
    "list_chains",
]
