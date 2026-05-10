"""Trends monitor — long-running market signals (analyst + research feeds)."""

from fastapi import APIRouter, Depends, Query

from ..deps import auth_dep
from ..services import news_service

router = APIRouter()


@router.get("")
def list_trends(
    limit: int = Query(default=100, ge=1, le=500),
    _=Depends(auth_dep),
) -> list[dict]:
    return news_service.list_trends(limit=limit)


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "trends", "batch": 4, "status": "active"}
