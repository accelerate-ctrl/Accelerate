"""News + trends watch — local seed (dev) / RSS (live)."""

from fastapi import APIRouter, Depends, Query

from ..deps import auth_dep
from ..services import news_service

router = APIRouter()


@router.get("")
def list_news(
    sub_cap_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _=Depends(auth_dep),
) -> list[dict]:
    return news_service.list_news(limit=limit, sub_cap_id=sub_cap_id)


@router.post("/refresh")
def refresh(_=Depends(auth_dep)) -> dict:
    return news_service.refresh().__dict__


@router.get("/runs/latest")
def latest_run(_=Depends(auth_dep)) -> dict | None:
    return news_service.latest_run()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "news", "batch": 4, "status": "active"}
