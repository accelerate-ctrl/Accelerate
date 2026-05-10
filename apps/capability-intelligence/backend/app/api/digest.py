"""Quarterly Strategic Digest — generate, browse, PPTX export."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from ..deps import auth_dep
from ..services import digest_service, pptx_export

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "digest", "batch": 7, "status": "active"}


@router.get("")
def list_digests(
    subvertical: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    _=Depends(auth_dep),
) -> list[dict]:
    return digest_service.list_digests(subvertical=subvertical, limit=limit)


class GenerateBody(BaseModel):
    subvertical: str
    period: str
    priority_limit: int = 5


@router.post("/generate")
def generate(body: GenerateBody, _=Depends(auth_dep)) -> dict:
    digest = digest_service.generate(
        subvertical=body.subvertical,
        period=body.period,
        priority_limit=body.priority_limit,
    )
    return asdict(digest)


@router.get("/{digest_id}")
def detail(digest_id: str, _=Depends(auth_dep)) -> dict:
    rec = digest_service.get_digest(digest_id)
    if not rec:
        raise HTTPException(status_code=404, detail="digest not found")
    return rec


@router.get("/{digest_id}/pptx")
def pptx(digest_id: str, _=Depends(auth_dep)) -> Response:
    rec = digest_service.get_digest(digest_id)
    if not rec:
        raise HTTPException(status_code=404, detail="digest not found")
    blob = pptx_export.render(rec)
    filename = f"{digest_id}.pptx"
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
