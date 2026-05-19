"""Drive / Sheets ingestion — discover, refresh per pillar or all, status, upload."""
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..deps import auth_dep
from ..services import catalogue_service as svc

router = APIRouter()

VALID_PILLARS = {"P1", "P2", "P3", "P4"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB — v7.0 workbooks are 5-15 MB each.


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


@router.get("/state")
def catalogue_state(_=Depends(auth_dep)) -> dict:
    """Per-pillar ingest version — what's loaded right now in Firestore.

    Drives the manual-upload widget so each drop zone can show its current
    file name + ingest timestamp + row counts. Maps to the `pillars`
    collection plus the latest ingest run.
    """
    pillars = svc.list_pillars()
    by_id: dict[str, dict] = {p.get("pillar_id"): p for p in pillars}
    runs = svc.list_ingest_runs(limit=20)
    # Find each pillar's most recent ingest run.
    last_run_by_pillar: dict[str, dict] = {}
    for run in runs:
        for pid in run.get("pillars_loaded", []) or []:
            if pid not in last_run_by_pillar:
                last_run_by_pillar[pid] = run

    out = []
    for pid in ("P1", "P2", "P3", "P4"):
        p = by_id.get(pid) or {"pillar_id": pid, "name": pid, "schema_status": "missing"}
        last_run = last_run_by_pillar.get(pid)
        out.append({
            "pillar_id": pid,
            "name": p.get("name", pid),
            "schema_status": p.get("schema_status", "missing"),
            "source_file_name": p.get("source_file_name"),
            "source_version": p.get("source_version"),
            "ingested_at": p.get("ingested_at"),
            "ingested_by": p.get("ingested_by"),
            "row_counts": (last_run or {}).get("counts_by_pillar", {}).get(pid, {}),
            "last_run_id": (last_run or {}).get("run_id"),
        })
    return {"pillars": out, "as_of": datetime.utcnow().isoformat()}


@router.post("/upload")
async def upload_pillar(
    pillar_id: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(auth_dep),
) -> dict:
    """Manual upload of a single pillar workbook (P1/P2/P3/P4).

    Used by the Settings → Pillar workbooks widget. Required while the v7.0
    Drive copies are pending pillar-lead approval — pillar leads can drop
    their .xlsx here without waiting for the Drive folder to be canonical.
    """
    if pillar_id not in VALID_PILLARS:
        raise HTTPException(400, f"pillar_id must be one of {sorted(VALID_PILLARS)}")
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "file must be .xlsx or .xlsm")
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "empty upload")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"file exceeds {MAX_UPLOAD_BYTES // (1024*1024)} MB cap")
    result = svc.ingest_uploaded_workbook(
        pillar_id=pillar_id, file_name=file.filename, content=content, by=user.email,
    )
    return _result_to_dict(result)


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
