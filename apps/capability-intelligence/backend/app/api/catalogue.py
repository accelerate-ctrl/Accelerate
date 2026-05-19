"""Catalogue browsing — pillars / categories / L1 / subcaps / use cases / L3 / L4 / themes."""
from fastapi import APIRouter, Depends, HTTPException

from ..deps import auth_dep
from ..services import catalogue_service as svc
from ..services.catalogue_service import COLLECTIONS

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
    from ..services.repository import get_repository
    sub = svc.get_subcap(sub_cap_id)
    if not sub:
        raise HTTPException(404, f"sub_cap_id not found: {sub_cap_id}")
    sow_mentions = sow_service.list_mentions_for_subcap(sub_cap_id)
    canonical = stories_service.list_canonical({"sub_cap_id": sub_cap_id}, limit=50)
    jira = stories_service.list_jira({"sub_cap_id": sub_cap_id}, limit=50)

    # v7.0 extended joins (Phase 1.3) — surface the offering /
    # data-product / completeness / cross-pillar coverage rows that
    # mention this subcap so the Subcap Deep Dive can render every
    # spec'd section without a per-section roundtrip.
    repo = get_repository()
    offerings = repo.list(COLLECTIONS["offering_subcap_matrix"], {"sub_cap_id": sub_cap_id})
    data_products = repo.list(COLLECTIONS["dataproduct_subcap_matrix"], {"sub_cap_id": sub_cap_id})
    completeness = repo.get(COLLECTIONS["completeness"], sub_cap_id)
    coverage = repo.get(COLLECTIONS["cross_pillar_coverage"], sub_cap_id)
    cascade_sim = repo.get(COLLECTIONS["cascade_simulation"], sub_cap_id)

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
        # v7.0 sections
        "offerings": offerings,
        "data_products": data_products,
        "completeness": completeness,
        "cross_pillar_coverage": coverage,
        "cascade_simulation": cascade_sim,
    }


# ─── v7.0 list endpoints (Phase 1.3) — wired into Vendor Intelligence /
#     Use Case Explorer / Cross-Pillar pages ──────────────────────────────


@router.get("/offerings")
def list_offerings(_=Depends(auth_dep)) -> list[dict]:
    """Productized offerings (workbook tab 10). De-dup across pillars."""
    from ..services.repository import get_repository
    seen: dict[str, dict] = {}
    for row in get_repository().list(COLLECTIONS["offerings"]):
        oid = row.get("offering_id")
        if oid and oid not in seen:
            seen[oid] = row
    return list(seen.values())


@router.get("/data-products")
def list_data_products(_=Depends(auth_dep)) -> list[dict]:
    """Data products (workbook tab 11). De-dup across pillars."""
    from ..services.repository import get_repository
    seen: dict[str, dict] = {}
    for row in get_repository().list(COLLECTIONS["data_products"]):
        mid = row.get("module_id")
        if mid and mid not in seen:
            seen[mid] = row
    return list(seen.values())


@router.get("/agentforce-agents")
def list_agentforce_agents(_=Depends(auth_dep)) -> list[dict]:
    """AI agents catalogued from the workbook (tab 8)."""
    from ..services.repository import get_repository
    return get_repository().list(COLLECTIONS["agentforce_agents"])


@router.get("/platform-constructs")
def list_platform_constructs(_=Depends(auth_dep)) -> list[dict]:
    """Reusable platform constructs (tab 9)."""
    from ..services.repository import get_repository
    return get_repository().list(COLLECTIONS["platform_constructs"])


@router.get("/cross-pillar-stories")
def list_cross_pillar_stories(
    pillar_id: str | None = None,
    sub_cap_id: str | None = None,
    limit: int = 100,
    _=Depends(auth_dep),
) -> list[dict]:
    """Cross-pillar stories (tab 14).

    ``pillar_id`` filters by the destination pillar (the pillar this
    story affects). ``sub_cap_id`` further narrows to stories whose
    ``linked_sub_caps`` includes the given id.
    """
    from ..services.repository import get_repository
    rows = get_repository().list(COLLECTIONS["cross_pillar_stories"])
    if pillar_id:
        rows = [r for r in rows if r.get("destination_pillar_id") == pillar_id]
    if sub_cap_id:
        rows = [r for r in rows if sub_cap_id in (r.get("linked_sub_caps") or [])]
    return rows[:limit]


@router.get("/completeness/{sub_cap_id}")
def get_completeness(sub_cap_id: str, _=Depends(auth_dep)) -> dict:
    """Authoritative workbook-curated completeness profile for a subcap."""
    from ..services.repository import get_repository
    row = get_repository().get(COLLECTIONS["completeness"], sub_cap_id)
    if row is None:
        raise HTTPException(404, f"no completeness row for {sub_cap_id}")
    return row


@router.get("/l3-platforms")
def get_l3(_=Depends(auth_dep)) -> list[dict]:
    return svc.list_l3()


@router.get("/maturity-distribution")
def maturity_distribution(
    pillar_id: str | None = None,
    _=Depends(auth_dep),
) -> dict:
    """How many subcaps reach each of the 5 maturity tiers (deepest
    non-empty descriptor wins). Powers the at-a-glance band counters on
    Capability Explorer."""
    rows = svc.list_maturity()
    if pillar_id:
        # subcap_id format is "P1C1.1.1" → first 2 chars = pillar id
        rows = [r for r in rows if (r.get("sub_cap_id") or "").startswith(pillar_id)]
    counts = {f"m{i}": 0 for i in range(1, 6)}
    for r in rows:
        # Find the deepest M-band with a descriptor.
        deepest = 0
        for i in range(1, 6):
            if r.get(f"m{i}"):
                deepest = i
        if deepest:
            counts[f"m{deepest}"] += 1
    total = sum(counts.values())
    return {
        "total_with_maturity": total,
        "by_level": counts,
        "labels": {
            "m1": "Foundational",
            "m2": "Developing",
            "m3": "Established",
            "m4": "Advanced",
            "m5": "Transformational",
        },
    }


@router.get("/structure")
def get_structure(_=Depends(auth_dep)) -> dict:
    """Hierarchical catalogue structure for Mission Control + Explorer
    breakdown views.

    Returns one entry per ingested pillar with subcap counts at every
    level so the UI can render the **Pillar → Category → L1 → Subcap**
    tree without doing N round-trips:

      {
        "pillars": [
          {
            "pillar_id": "P1", "name": "...", "schema_status": "...",
            "version": "v6.8", "source_file_name": "...",
            "subcap_total": 199, "l1_total": 36, "category_total": 4,
            "categories": [
              {
                "category_id": "P1C1", "name": "...",
                "subcap_total": 50, "l1_total": 9,
                "l1s": [
                  {
                    "l1_capability": "Adoption Management",
                    "subcap_count": 7, "active_subcap_count": 5,
                    "subcaps": [
                      {"sub_cap_id": "P1C1.1.1",
                       "sub_cap_name": "...",
                       "zennify_status": "active"}, …
                    ],
                  }, …
                ],
              }, …
            ],
          }, …
        ],
        "totals": {"pillars": 3, "subcaps": 650, "l1s": 102, "categories": 12}
      }
    """
    pillars = svc.list_pillars()
    cats = svc.list_categories()
    subs = svc.list_subcaps()

    cats_by_id = {c.get("category_id"): c for c in cats}

    pillar_payload: list[dict] = []
    grand_subs = 0
    grand_l1s = 0
    grand_cats = 0
    for p in pillars:
        pid = p["pillar_id"]
        p_subs = [s for s in subs if (s.get("pillar_id") or "") == pid]
        p_cats = [c for c in cats if (c.get("pillar_id") or "") == pid]

        # Bucket by (category_id, l1_capability).
        l1_buckets: dict[tuple[str, str], list[dict]] = {}
        for s in p_subs:
            key = (s.get("category_id") or "?", s.get("l1_capability") or "Uncategorised")
            l1_buckets.setdefault(key, []).append(s)

        # Group buckets into categories.
        cat_payload: list[dict] = []
        cat_ids_seen = sorted({c.get("category_id") for c in p_cats if c.get("category_id")})
        # Make sure every L1 bucket's category gets a row even if the
        # category row is missing.
        for k in l1_buckets:
            if k[0] not in cat_ids_seen and k[0] != "?":
                cat_ids_seen.append(k[0])
        cat_ids_seen.sort()

        for cid in cat_ids_seen:
            cat_row = cats_by_id.get(cid) or {}
            l1_payload: list[dict] = []
            cat_sub_total = 0
            for (lc_id, l1_name), bucket in sorted(l1_buckets.items()):
                if lc_id != cid:
                    continue
                bucket_sorted = sorted(bucket, key=lambda s: s.get("sub_cap_id") or "")
                active = sum(
                    1 for s in bucket_sorted
                    if (s.get("zennify_status") or "").lower() == "active"
                )
                l1_payload.append({
                    "l1_capability": l1_name,
                    "subcap_count": len(bucket_sorted),
                    "active_subcap_count": active,
                    "subcaps": [
                        {
                            "sub_cap_id": s.get("sub_cap_id"),
                            "sub_cap_name": s.get("sub_cap_name") or s.get("name"),
                            "zennify_status": s.get("zennify_status") or "active",
                        }
                        for s in bucket_sorted
                    ],
                })
                cat_sub_total += len(bucket_sorted)
            cat_payload.append({
                "category_id": cid,
                "name": cat_row.get("name") or cat_row.get("category_name") or cid,
                "subcap_total": cat_sub_total,
                "l1_total": len(l1_payload),
                "l1s": l1_payload,
            })

        l1_total = sum(c["l1_total"] for c in cat_payload)
        sub_total = sum(c["subcap_total"] for c in cat_payload)
        pillar_payload.append({
            "pillar_id": pid,
            "name": p.get("name") or pid,
            "schema_status": p.get("schema_status"),
            "version": p.get("source_version") or p.get("parsed_version"),
            "source_file_name": p.get("source_file_name"),
            "subcap_total": sub_total,
            "l1_total": l1_total,
            "category_total": len(cat_payload),
            "categories": cat_payload,
        })
        grand_subs += sub_total
        grand_l1s += l1_total
        grand_cats += len(cat_payload)

    return {
        "pillars": pillar_payload,
        "totals": {
            "pillars": len(pillar_payload),
            "subcaps": grand_subs,
            "l1s": grand_l1s,
            "categories": grand_cats,
        },
    }


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
            # Lifecycle state is computed by lifecycle_service and lives
            # in the lifecycle_states/{sub_cap_id} collection. The
            # structure endpoint returns whatever was joined in by the
            # caller; default to null so the FE knows to look it up.
            "lifecycle_state": s.get("lifecycle_state"),
        })
    out_pillars = []
    for pid, pnode in sorted(by_p.items()):
        cats = []
        for cid, cnode in sorted(pnode["categories"].items()):
            l1s = [{"name": k, "subcaps": v["subcaps"]} for k, v in sorted(cnode["l1"].items())]
            cats.append({"category_id": cid, "name": cnode["name"], "l1": l1s})
        out_pillars.append({"pillar_id": pid, "name": pnode["name"], "categories": cats})
    return {"pillars": out_pillars}
