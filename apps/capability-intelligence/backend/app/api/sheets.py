"""Drive / Sheets ingestion — discover, refresh per pillar or all, status."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..deps import auth_dep
from ..services import catalogue_service as svc

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "sheets", "batch": 1, "status": "active"}


@router.get("/discover")
def discover(_=Depends(auth_dep)) -> dict:
    """List the pillar files the Drive watcher would ingest, without parsing."""
    files = svc.discover_pillar_files()
    return {
        "pillars": [
            {
                "pillar_id": pid,
                "file_id": f.file_id,
                "file_name": f.file_name,
                "modified_at": f.modified_at.isoformat() if isinstance(f.modified_at, datetime) else str(f.modified_at),
                "parsed_version": f.parsed_version,
                "is_google_sheet": f.is_google_sheet,
                "source": f.source,
            }
            for pid, f in sorted(files.items())
        ],
        "discovered_at": datetime.utcnow().isoformat(),
    }


@router.post("/refresh")
def refresh_all(user=Depends(auth_dep)) -> dict:
    return _result_to_dict(svc.refresh_all_pillars(by=user.email))


@router.post("/refresh/{pillar_id}")
def refresh_one(pillar_id: str, user=Depends(auth_dep)) -> dict:
    if not pillar_id.startswith("P"):
        raise HTTPException(400, "pillar_id must look like P1..P4")
    return _result_to_dict(svc.refresh_pillar(pillar_id, by=user.email))


@router.get("/runs")
def list_runs(limit: int = 20, _=Depends(auth_dep)) -> list[dict]:
    return svc.list_ingest_runs(limit=limit)


def _result_to_dict(r) -> dict:
    return {
        "run_id": r.run_id,
        "started_at": r.started_at.isoformat(),
        "completed_at": r.completed_at.isoformat(),
        "pillars_attempted": r.pillars_attempted,
        "pillars_loaded": r.pillars_loaded,
        "pillars_skipped": r.pillars_skipped,
        "counts_by_pillar": r.counts_by_pillar,
        "flags_raised": [f["flag_id"] for f in r.flags_raised],
    }
