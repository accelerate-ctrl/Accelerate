"""AI suggestion lifecycle: list / get / apply / reject + stats."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

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
    origin: str | None = Query(
        default=None,
        description="loop | news | partner | audit | what-if",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    _=Depends(auth_dep),
) -> list[dict]:
    return suggestions_service.list_suggestions(
        status=status,
        sub_cap_id=sub_cap_id,
        origin=origin,
        limit=limit,
    )


@router.get("/stats")
def stats(_=Depends(auth_dep)) -> dict:
    return suggestions_service.stats()


@router.get("/origins")
def origins(_=Depends(auth_dep)) -> dict:
    """Distinct origin counts so the FE filter chips render only origins
    that actually have rows."""
    return {"origins": suggestions_service.list_origins()}


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


class BulkRejectBody(BaseModel):
    """Reject multiple suggestions in one call (IMP-11).

    Per App Flow J3, every rejection requires a non-empty rationale so
    the same reason doesn't poison future cycles — the bulk endpoint
    enforces ``reason`` at the API edge via Pydantic min_length=1.
    """
    ids: list[str] = Field(..., min_length=1, max_length=200)
    reason: str = Field(..., min_length=1)


@router.post("/bulk-reject")
def bulk_reject(body: BulkRejectBody, user=Depends(auth_dep)) -> dict:
    """Reject up to 200 pending suggestions with a shared reason."""
    actor = getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else str(user))
    try:
        return suggestions_service.bulk_reject(body.ids, actor, reason=body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
