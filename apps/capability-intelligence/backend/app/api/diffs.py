"""Version diffs."""
from fastapi import APIRouter, Depends

from ..deps import auth_dep
from ..services import version_service as svc

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "diffs", "batch": 1, "status": "active"}


@router.get("/{version_a}/{version_b}")
def diff(version_a: str, version_b: str, _=Depends(auth_dep)) -> dict:
    return svc.diff_versions(version_a, version_b)
