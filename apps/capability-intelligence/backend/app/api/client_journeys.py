"""Client Journey Atlas + DMA App handoff."""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import auth_dep
from ..services import client_journey_service

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "client_journeys", "batch": 6, "status": "active"}


@router.get("")
def list_journeys(
    limit: int = Query(default=100, ge=1, le=500),
    _=Depends(auth_dep),
) -> list[dict]:
    return client_journey_service.list_journeys(limit=limit)


@router.post("/refresh")
def refresh(_=Depends(auth_dep)) -> dict:
    return client_journey_service.refresh_all()


@router.get("/{client_name}/journey")
def journey(client_name: str, _=Depends(auth_dep)) -> dict:
    rec = client_journey_service.get_journey(client_name)
    if not rec:
        raise HTTPException(status_code=404, detail="client not found")
    return rec


@router.get("/{client_name}/dma-packet")
def dma_packet(client_name: str, _=Depends(auth_dep)) -> dict:
    rec = client_journey_service.dma_packet(client_name)
    if not rec:
        raise HTTPException(status_code=404, detail="client not found")
    return rec
