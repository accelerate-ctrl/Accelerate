"""Story Library — canonical (gen) + Jira + raw Pillar-1 sheet."""
from fastapi import APIRouter, Depends, HTTPException

from ..deps import auth_dep
from ..services import stories_service as svc

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "stories", "batch": 3, "status": "active"}


@router.post("/refresh")
def refresh(user=Depends(auth_dep)) -> dict:
    r = svc.refresh_all(by=user.email)
    return {
        "run_id": r.run_id,
        "started_at": r.started_at.isoformat(),
        "completed_at": r.completed_at.isoformat(),
        "canonical_loaded": r.canonical_loaded,
        "jira_loaded": r.jira_loaded,
        "canonical_source": r.canonical_source,
        "jira_source": r.jira_source,
        "schema_issues": r.schema_issues,
    }


@router.get("/runs")
def runs(limit: int = 20, _=Depends(auth_dep)) -> list[dict]:
    return svc.list_runs(limit=limit)


@router.get("/canonical")
def canonical(sub_cap_id: str | None = None, limit: int = 200, _=Depends(auth_dep)) -> list[dict]:
    return svc.list_canonical({"sub_cap_id": sub_cap_id} if sub_cap_id else None, limit=limit)


@router.get("/jira")
def jira(sub_cap_id: str | None = None, limit: int = 200, _=Depends(auth_dep)) -> list[dict]:
    return svc.list_jira({"sub_cap_id": sub_cap_id} if sub_cap_id else None, limit=limit)


@router.get("/by-subcap/{sub_cap_id}")
def by_subcap(sub_cap_id: str, _=Depends(auth_dep)) -> dict:
    return svc.list_stories_for_subcap(sub_cap_id)


@router.get("/{story_key}")
def get_story(story_key: str, _=Depends(auth_dep)) -> dict:
    s = svc.get_story(story_key)
    if not s:
        raise HTTPException(404, f"story not found: {story_key}")
    return s
