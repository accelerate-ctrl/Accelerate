"""RAG chat — vector retrieval + Batch-4 consultant loop."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
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


@router.get("")
def list_conversations(limit: int = 50, _=Depends(auth_dep)) -> list[dict]:
    return chat_service.list_conversations(limit=limit)


@router.get("/{conversation_id}")
def detail(conversation_id: str, _=Depends(auth_dep)) -> dict:
    rec = chat_service.get_conversation(conversation_id)
    if not rec:
        raise HTTPException(status_code=404, detail="conversation not found")
    return rec
