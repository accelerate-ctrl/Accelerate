"""AI suggestion lifecycle: list / get / apply / reject + stats."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import auth_dep
from ..services import suggestions_service

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "suggestions", "batch": 4, "status": "active"}


@router.get("")
def list_suggestions(
    status: str | None = Query(default=None),
    sub_cap_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _=Depends(auth_dep),
) -> list[dict]:
    return suggestions_service.list_suggestions(status=status, sub_cap_id=sub_cap_id, limit=limit)


@router.get("/stats")
def stats(_=Depends(auth_dep)) -> dict:
    return suggestions_service.stats()


@router.get("/{sug_id}")
def get(sug_id: str, _=Depends(auth_dep)) -> dict:
    sug = suggestions_service.get_suggestion(sug_id)
    if not sug:
        raise HTTPException(status_code=404, detail="suggestion not found")
    return sug


class DecisionBody(BaseModel):
    reason: str | None = None


@router.post("/{sug_id}/apply")
def apply(sug_id: str, body: DecisionBody, user=Depends(auth_dep)) -> dict:
    actor = getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else str(user))
    try:
        return suggestions_service.apply_suggestion(sug_id, actor)
    except KeyError:
        raise HTTPException(status_code=404, detail="suggestion not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/{sug_id}/reject")
def reject(sug_id: str, body: DecisionBody, user=Depends(auth_dep)) -> dict:
    actor = getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else str(user))
    try:
        return suggestions_service.reject_suggestion(sug_id, actor, reason=body.reason or "")
    except KeyError:
        raise HTTPException(status_code=404, detail="suggestion not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
