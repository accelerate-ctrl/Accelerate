"""Multi-lens projections — value chain, subvertical, maturity, UC, platforms."""
from fastapi import APIRouter, Depends

from ..deps import auth_dep
from ..services import lens_service as ls

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "lens", "batch": 2, "status": "active"}


@router.get("/subverticals")
def subverticals(_=Depends(auth_dep)) -> list[dict]:
    return ls.subverticals()


@router.get("/clusters")
def clusters(_=Depends(auth_dep)) -> list[dict]:
    return ls.vcc_clusters()


@router.get("/uc-tag-families")
def uc_tag_families(_=Depends(auth_dep)) -> list[dict]:
    return ls.uc_tag_families()


@router.get("/value-chain-atlas")
def value_chain_atlas(subvertical_code: str | None = None, _=Depends(auth_dep)) -> dict:
    return ls.value_chain_atlas(subvertical_code=subvertical_code)


@router.get("/subvertical-compare/{sub_cap_id}")
def subvertical_compare(sub_cap_id: str, _=Depends(auth_dep)) -> dict:
    return ls.subvertical_compare(sub_cap_id=sub_cap_id)


@router.get("/subvertical-gaps")
def subvertical_gaps(
    from_code: str,
    to_code: str,
    pillar_id: str | None = None,
    _=Depends(auth_dep),
) -> dict:
    """Asymmetric subcap coverage: subcaps tagged for `from` but not for
    `to` (and vice-versa). Drives the Subvertical Compare gap view."""
    return ls.subvertical_gaps(from_code, to_code, pillar_id)


@router.get("/maturity-heatmap")
def maturity_heatmap(pillar_id: str | None = None, _=Depends(auth_dep)) -> dict:
    return ls.maturity_heatmap(pillar_id=pillar_id)


@router.get("/use-case-explorer")
def use_case_explorer(_=Depends(auth_dep)) -> dict:
    return ls.use_case_explorer()


@router.get("/platform-catalog")
def platform_catalog(_=Depends(auth_dep)) -> dict:
    return ls.platform_catalog()
