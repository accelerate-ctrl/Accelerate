"""Catalogue browsing — pillars / categories / L1 / subcaps / use cases / L3 / L4 / themes."""
from fastapi import APIRouter, Depends, HTTPException

from ..deps import auth_dep
from ..services import catalogue_service as svc

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "catalogue", "batch": 1, "status": "active"}


@router.get("/pillars")
def get_pillars(_=Depends(auth_dep)) -> list[dict]:
    return svc.list_pillars()


@router.get("/overview")
def get_overview(_=Depends(auth_dep)) -> dict:
    """Mission Control payload: pillar tiles + counts + last ingest."""
    pillars = svc.list_pillars()
    subcaps_all = svc.list_subcaps()
    by_pillar: dict[str, dict] = {}
    for p in pillars:
        pid = p["pillar_id"]
        sub_for = [s for s in subcaps_all if s.get("pillar_id") == pid]
        cats = svc.list_categories(pid)
        by_pillar[pid] = {
            "pillar": p,
            "category_count": len(cats),
            "subcap_count": len(sub_for),
            "active_subcaps": sum(1 for s in sub_for if (s.get("zennify_status") or "").lower() == "active"),
        }
    runs = svc.list_ingest_runs(limit=1)
    open_flag_count = len(svc.list_flags(open_only=True))
    return {
        "pillars": by_pillar,
        "totals": {
            "pillars_loaded": len([p for p in pillars if p.get("schema_status") == "complete"]),
            "subcaps": len(subcaps_all),
            "open_flags": open_flag_count,
        },
        "last_ingest": runs[0] if runs else None,
    }


@router.get("/categories")
def get_categories(pillar_id: str | None = None, _=Depends(auth_dep)) -> list[dict]:
    return svc.list_categories(pillar_id)


@router.get("/subcaps")
def get_subcaps(pillar_id: str | None = None, _=Depends(auth_dep)) -> list[dict]:
    return svc.list_subcaps(pillar_id)


@router.get("/subcaps/{sub_cap_id}")
def get_subcap(sub_cap_id: str, _=Depends(auth_dep)) -> dict:
    from ..services import sow_service, stories_service
    sub = svc.get_subcap(sub_cap_id)
    if not sub:
        raise HTTPException(404, f"sub_cap_id not found: {sub_cap_id}")
    sow_mentions = sow_service.list_mentions_for_subcap(sub_cap_id)
    canonical = stories_service.list_canonical({"sub_cap_id": sub_cap_id}, limit=50)
    jira = stories_service.list_jira({"sub_cap_id": sub_cap_id}, limit=50)
    return {
        "subcap": sub,
        "maturity": svc.get_maturity(sub_cap_id),
        "l4_features": svc.list_l4_for(sub_cap_id),
        "use_cases": svc.list_use_cases_for(sub_cap_id),
        "themes": svc.list_themes_for(sub_cap_id),
        "stories": svc.list_stories_for(sub_cap_id),
        "sow_signals": {
            "mention_count": len(sow_mentions),
            "mentions": sow_mentions,
            "client_count": len({m.get("client_name") for m in sow_mentions if m.get("client_name")}),
        },
        "story_signals": {
            "canonical_count": len(canonical),
            "jira_count": len(jira),
            "canonical": canonical[:10],
            "jira": jira[:10],
        },
    }


@router.get("/l3-platforms")
def get_l3(_=Depends(auth_dep)) -> list[dict]:
    return svc.list_l3()


@router.get("/tree")
def get_tree(pillar_id: str | None = None, _=Depends(auth_dep)) -> dict:
    """Hierarchical tree for sunburst / collapsible-tree rendering."""
    pillars = svc.list_pillars()
    subcaps = svc.list_subcaps(pillar_id)
    by_p: dict[str, dict] = {}
    for s in subcaps:
        p = by_p.setdefault(s["pillar_id"], {
            "pillar_id": s["pillar_id"],
            "name": next((p["name"] for p in pillars if p["pillar_id"] == s["pillar_id"]), s["pillar_id"]),
            "categories": {},
        })
        c = p["categories"].setdefault(s.get("category_id", "?"), {
            "category_id": s.get("category_id", "?"),
            "name": s.get("category_id", "?"),
            "l1": {},
        })
        l1 = c["l1"].setdefault(s.get("l1_capability", "?"), {
            "name": s.get("l1_capability", "?"),
            "subcaps": [],
        })
        l1["subcaps"].append({
            "sub_cap_id": s["sub_cap_id"],
            "sub_cap_name": s["sub_cap_name"],
            "tier": s.get("tier"),
            "lifecycle_state": s.get("lifecycle_state", "active"),
        })
    out_pillars = []
    for pid, pnode in sorted(by_p.items()):
        cats = []
        for cid, cnode in sorted(pnode["categories"].items()):
            l1s = [{"name": k, "subcaps": v["subcaps"]} for k, v in sorted(cnode["l1"].items())]
            cats.append({"category_id": cid, "name": cnode["name"], "l1": l1s})
        out_pillars.append({"pillar_id": pid, "name": pnode["name"], "categories": cats})
    return {"pillars": out_pillars}
