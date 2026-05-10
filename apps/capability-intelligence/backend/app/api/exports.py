"""XLSX exports — catalogue / lifecycle / clients / benchmarks."""

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..deps import auth_dep
from ..services import exports_service

router = APIRouter()

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "exports", "batch": 8, "status": "active"}


@router.get("/catalogue.xlsx")
def catalogue(_=Depends(auth_dep)) -> Response:
    return _xlsx(exports_service.export_catalogue(), "catalogue.xlsx")


@router.get("/lifecycle.xlsx")
def lifecycle(_=Depends(auth_dep)) -> Response:
    return _xlsx(exports_service.export_lifecycle(), "lifecycle.xlsx")


@router.get("/clients.xlsx")
def clients(_=Depends(auth_dep)) -> Response:
    return _xlsx(exports_service.export_clients(), "clients.xlsx")


@router.get("/benchmarks.xlsx")
def benchmarks(_=Depends(auth_dep)) -> Response:
    return _xlsx(exports_service.export_benchmarks(), "benchmarks.xlsx")


def _xlsx(blob: bytes, filename: str) -> Response:
    return Response(
        content=blob,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
