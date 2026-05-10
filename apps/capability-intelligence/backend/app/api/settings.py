"""Settings — current-effective config + a few user-tunables."""
from fastapi import APIRouter, Depends

from ..config import get_settings
from ..deps import auth_dep

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "settings", "batch": 1, "status": "active"}


@router.get("")
def get_effective(_=Depends(auth_dep)) -> dict:
    s = get_settings()
    return {
        "env": s.env,
        "auth_mode": s.auth_mode,
        "auth_allowed_domain": s.auth_allowed_domain,
        "use_gcp": s.use_gcp,
        "gcp_project_id": s.gcp_project_id,
        "gcp_region": s.gcp_region,
        "firestore_database_id": s.firestore_database_id,
        "drive_pillars_folder_id": s.drive_pillars_folder_id,
        "local_catalogue_dir": s.local_catalogue_dir,
        # cost guardrails (Batch 4 will use these)
        "daily_spend_ceiling_usd": s.daily_spend_ceiling_usd,
        "anthropic_weekly_budget_usd": s.anthropic_weekly_budget_usd,
    }
