"""SOW Library — ingestion, browse, mentions, redacted previews."""
from fastapi import APIRouter, Depends, HTTPException

from ..deps import auth_dep
from ..services import sow_service as svc

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "sows", "batch": 3, "status": "active"}


@router.get("/discover")
def discover(_=Depends(auth_dep)) -> dict:
    files = svc.discover_sows()
    return {
        "files": [
            {
                "sow_id": f.sow_id,
                "file_name": f.file_name,
                "file_uri": f.file_uri,
                "status": f.status,
                "source": f.source,
                "modified_at": f.modified_at.isoformat(),
            }
            for f in files
        ]
    }


@router.post("/refresh")
def refresh(user=Depends(auth_dep)) -> dict:
    r = svc.ingest_all(by=user.email)
    return _result_to_dict(r)


@router.get("")
def list_sows(status: str | None = None, client: str | None = None, _=Depends(auth_dep)) -> list[dict]:
    return svc.list_sows(status=status, client=client)


@router.get("/runs")
def list_runs(limit: int = 20, _=Depends(auth_dep)) -> list[dict]:
    return svc.list_ingest_runs(limit=limit)


@router.get("/clients")
def list_clients(_=Depends(auth_dep)) -> list[dict]:
    return svc.list_clients()


@router.get("/{sow_id}")
def get_sow(sow_id: str, _=Depends(auth_dep)) -> dict:
    sow = svc.get_sow(sow_id)
    if not sow:
        raise HTTPException(404, f"sow not found: {sow_id}")
    return {
        "sow": sow,
        "mentions": svc.list_mentions_for_sow(sow_id),
    }


@router.get("/{sow_id}/preview")
def preview(sow_id: str, max_chars: int = 4000, _=Depends(auth_dep)) -> dict:
    sow = svc.get_sow(sow_id)
    if not sow:
        raise HTTPException(404, f"sow not found: {sow_id}")
    chunks = svc.list_chunks_for(sow_id)
    text = "\n\n".join(c["text"] for c in chunks)
    return {
        "sow_id": sow_id,
        "file_name": sow["file_name"],
        "redaction_method": sow.get("redaction_method"),
        "redaction_summary": sow.get("redaction_summary"),
        "preview": text[:max_chars],
        "truncated": len(text) > max_chars,
    }


def _result_to_dict(r) -> dict:
    return {
        "run_id": r.run_id,
        "started_at": r.started_at.isoformat(),
        "completed_at": r.completed_at.isoformat(),
        "files_attempted": r.files_attempted,
        "sows_loaded": r.sows_loaded,
        "chunks_total": r.chunks_total,
        "mentions_total": r.mentions_total,
        "redactions_total": r.redactions_total,
        "sow_ids": r.sow_ids,
    }
