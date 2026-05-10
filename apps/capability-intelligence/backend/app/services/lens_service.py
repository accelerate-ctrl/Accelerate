"""Multi-lens projections of the catalogue.

Powers Value Chain Atlas, Subvertical Compare, Maturity Heatmap, Use Case
Explorer, Platform Catalog. Each function returns a JSON-friendly payload
ready for direct render.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from . import catalogue_service as cat
from .graph_service import (
    _load_subverticals,
    _load_uc_tag_families,
    _load_vcc_clusters,
    classify_stage,
    extract_uc_tag,
    family_for_tag,
)


# ─── Reference loaders (frontend asks for these too) ─────────────────────────


def lens_definitions() -> list[dict]:
    return cat.list_l3.__module__ and []  # placeholder; real list comes from yaml in api layer


def subverticals() -> list[dict]:
    return _load_subverticals()


def vcc_clusters() -> list[dict]:
    return _load_vcc_clusters()


def uc_tag_families() -> list[dict]:
    return _load_uc_tag_families()


# ─── Value Chain Atlas ───────────────────────────────────────────────────────


def value_chain_atlas(subvertical_code: str | None = None) -> dict:
    """Group all stage occurrences by VCC cluster, optionally filtered by SV.

    Returns: {clusters: [{code, name, color, stages: [{name, subvertical_code, subcap_count}], total_subcaps}]}
    """
    cluster_defs = _load_vcc_clusters()
    cluster_index = {c["code"]: c for c in cluster_defs}

    # subvertical_code -> stage_name -> {subcap_ids, cluster}
    by_stage: dict[tuple[str, str], dict] = {}
    for vc in cat.list_vc_mappings():
        sv = vc.get("subvertical_code")
        if subvertical_code and sv != subvertical_code:
            continue
        for raw in vc.get("stages", []):
            key = (sv, raw)
            entry = by_stage.setdefault(key, {"subvertical_code": sv, "name": raw, "cluster": classify_stage(raw, cluster_defs), "subcap_ids": set()})
            entry["subcap_ids"].add(vc["sub_cap_id"])

    by_cluster: dict[str, list[dict]] = defaultdict(list)
    for entry in by_stage.values():
        out = {
            "name": entry["name"],
            "subvertical_code": entry["subvertical_code"],
            "subcap_count": len(entry["subcap_ids"]),
            "subcap_ids": sorted(entry["subcap_ids"])[:50],
        }
        by_cluster[entry["cluster"]].append(out)

    payload_clusters = []
    for c in cluster_defs:
        stages = sorted(by_cluster.get(c["code"], []), key=lambda s: -s["subcap_count"])
        payload_clusters.append({
            "code": c["code"],
            "name": c["name"],
            "color": c.get("color"),
            "stages": stages,
            "total_subcaps": sum(s["subcap_count"] for s in stages),
        })
    return {"subvertical_code": subvertical_code, "clusters": payload_clusters}


# ─── Subvertical Compare ─────────────────────────────────────────────────────


def subvertical_compare(sub_cap_id: str) -> dict:
    """For a given subcap, show how it manifests across all 10 subverticals."""
    svs = _load_subverticals()
    cluster_defs = _load_vcc_clusters()
    rows = []
    for sv in svs:
        mapping = cat.list_vc_mappings({"sub_cap_id": sub_cap_id, "subvertical_code": sv["code"]})
        if mapping:
            stages = mapping[0].get("stages", [])
            tagged = [{"name": s, "cluster": classify_stage(s, cluster_defs)} for s in stages]
        else:
            tagged = []
        rows.append({
            "subvertical_code": sv["code"],
            "subvertical_name": sv["name"],
            "applicable": bool(tagged),
            "stages": tagged,
        })
    return {"sub_cap_id": sub_cap_id, "rows": rows}


# ─── Maturity Heatmap ────────────────────────────────────────────────────────


def maturity_heatmap(pillar_id: str | None = None) -> dict:
    """Return a 199 × 5 matrix for the heatmap."""
    rows = cat.list_maturity({"pillar_id": pillar_id} if pillar_id else None)
    out_rows = []
    levels = ["m1", "m2", "m3", "m4", "m5"]
    for r in rows:
        out_rows.append({
            "sub_cap_id": r.get("sub_cap_id"),
            "sub_cap_name": r.get("sub_cap_name"),
            "category_id": r.get("category_id"),
            "l1_capability": r.get("l1_capability"),
            "cells": [
                {
                    "level": lvl.upper(),
                    "filled": bool(r.get(lvl)),
                    "preview": (r.get(lvl) or "")[:140],
                }
                for lvl in levels
            ],
        })
    # Sort by category, then l1, then id for stable layout
    out_rows.sort(key=lambda x: (x.get("category_id") or "", x.get("l1_capability") or "", x.get("sub_cap_id") or ""))
    return {"pillar_id": pillar_id, "levels": [lvl.upper() for lvl in levels], "rows": out_rows}


# ─── Use Case Explorer ───────────────────────────────────────────────────────


def use_case_explorer() -> dict:
    """Group ~3000 use cases by archetype tag, then by 5-tag family."""
    fams = _load_uc_tag_families()
    tag_to_family = {tag: fam["id"] for fam in fams for tag in fam.get("tags", [])}
    family_index = {fam["id"]: fam for fam in fams}

    counter: Counter[tuple[str, str]] = Counter()  # (family, tag) -> count
    examples: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for uc in cat.list_use_cases():
        tag = uc.get("label") or extract_uc_tag(uc.get("description"))
        if not tag:
            continue
        fam = tag_to_family.get(tag, "unclassified")
        counter[(fam, tag)] += 1
        if len(examples[(fam, tag)]) < 3:
            examples[(fam, tag)].append({
                "use_case_id": uc.get("use_case_id"),
                "sub_cap_id": uc.get("sub_cap_id"),
                "description": uc.get("description"),
            })

    by_family: dict[str, dict] = {}
    for (fam_id, tag), n in counter.items():
        fam_meta = family_index.get(fam_id) or {"id": fam_id, "name": fam_id.title(), "color": "#999"}
        node = by_family.setdefault(fam_id, {
            "family_id": fam_id,
            "family_name": fam_meta.get("name", fam_id),
            "color": fam_meta.get("color"),
            "total": 0,
            "tags": [],
        })
        node["total"] += n
        node["tags"].append({"tag": tag, "count": n, "examples": examples[(fam_id, tag)]})
    families_out = sorted(by_family.values(), key=lambda f: -f["total"])
    for f in families_out:
        f["tags"].sort(key=lambda t: -t["count"])
    return {"families": families_out, "total_use_cases": sum(counter.values())}


# ─── Platform Catalog ────────────────────────────────────────────────────────


def platform_catalog() -> dict:
    """Group L3 platforms by vendor; count subcaps using each."""
    plats = cat.list_l3()

    # Count subcap → l3 occurrences (by L3 ID)
    subcaps = cat.list_subcaps()
    use_count: Counter[str] = Counter()
    for s in subcaps:
        seen_in_row: set[str] = set()
        for raw in s.get("l3_platforms", []) or []:
            import re
            m = re.search(r"\[(L3-[A-Za-z0-9_-]+)\]", str(raw))
            if not m:
                continue
            seen_in_row.add(m.group(1))
        for l3id in seen_in_row:
            use_count[l3id] += 1

    by_vendor: dict[str, list[dict]] = defaultdict(list)
    for p in plats:
        vendor = p.get("vendor") or "Unknown"
        by_vendor[vendor].append({
            "l3_id": p.get("l3_id"),
            "name": p.get("name"),
            "category": p.get("category"),
            "description": p.get("description"),
            "reference_url": p.get("reference_url"),
            "subcap_count": use_count.get(p.get("l3_id", ""), 0),
        })

    vendors_out = []
    for vendor, items in sorted(by_vendor.items(), key=lambda x: x[0].lower()):
        items.sort(key=lambda i: -i["subcap_count"])
        vendors_out.append({
            "vendor": vendor,
            "platform_count": len(items),
            "total_subcaps_using": sum(i["subcap_count"] for i in items),
            "platforms": items,
        })
    return {"vendors": vendors_out, "total_platforms": len(plats)}
