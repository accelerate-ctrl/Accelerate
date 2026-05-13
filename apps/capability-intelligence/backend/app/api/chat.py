"""RAG chat — vector retrieval + consultant loop + SSE streaming."""

import json
from dataclasses import asdict
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..deps import auth_dep
from ..services import chat_service

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "chat", "batch": 8, "status": "active"}


class MessageBody(BaseModel):
    message: str
    conversation_id: str | None = None


@router.post("/messages")
def post_message(body: MessageBody, _=Depends(auth_dep)) -> dict:
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")
    reply = chat_service.post_message(
        message=body.message,
        conversation_id=body.conversation_id,
    )
    return asdict(reply)


@router.post("/messages/stream")
def stream_message(body: MessageBody, _=Depends(auth_dep)) -> StreamingResponse:
    """Server-Sent Events flavour of POST /messages.

    The handler emits a sequence of events the SPA can render
    progressively. Today it's a synthetic-stream (one event per phase)
    because the underlying consultant loop is synchronous; we keep the
    SSE wire format so the front-end can hot-swap to a fully streaming
    loop later without changing the UI.

    Event types (each line: `event: <name>\\ndata: <json>\\n\\n`):
        * `retrieve` — { sources: [...] }
        * `chain`    — { chain_id, stage, started_at }
        * `reply`    — { reply, citations, cost_usd, error? }
        * `done`     — { conversation_id, message_id }
    """
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    async def _gen() -> AsyncGenerator[bytes, None]:
        # Phase 1 — retrieval (in-process, fast).
        try:
            preview = chat_service._retrieve(body.message)
        except Exception as exc:  # noqa: BLE001
            preview = []
            yield _sse("retrieve", {"sources": [], "error": str(exc)})
        else:
            yield _sse("retrieve", {"sources": [
                {"id": s.get("id"), "kind": s.get("kind"), "title": s.get("title"),
                 "url": s.get("url")}
                for s in preview[:12]
            ]})

        # Phase 2 — run the full consultant loop + capture the reply.
        reply = chat_service.post_message(
            message=body.message,
            conversation_id=body.conversation_id,
        )
        if reply.chain_id:
            yield _sse("chain", {
                "chain_id": reply.chain_id,
                "cost_usd": reply.cost_usd,
            })
        yield _sse("reply", {
            "reply": reply.reply,
            "citations": reply.citations,
            "cost_usd": reply.cost_usd,
            "error": reply.error,
        })
        yield _sse("done", {
            "conversation_id": reply.conversation_id,
            "message_id": reply.message_id,
        })

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering
        },
    )


def _sse(event: str, payload: dict) -> bytes:
    return (f"event: {event}\ndata: {json.dumps(payload)}\n\n").encode("utf-8")


@router.get("")
def list_conversations(limit: int = 50, _=Depends(auth_dep)) -> list[dict]:
    return chat_service.list_conversations(limit=limit)


@router.get("/{conversation_id}")
def detail(conversation_id: str, _=Depends(auth_dep)) -> dict:
    rec = chat_service.get_conversation(conversation_id)
    if not rec:
        raise HTTPException(status_code=404, detail="conversation not found")
    return rec
