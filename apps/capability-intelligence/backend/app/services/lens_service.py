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


def subvertical_gaps(from_code: str, to_code: str, pillar_id: str | None = None) -> dict:
    """Surfaces the asymmetric subcap coverage between two subverticals.

    Output:
      {
        "from": {"code", "name"},
        "to":   {"code", "name"},
        "common":    [sub_cap_id, ...],   # tagged for BOTH
        "only_in_from": [{sub_cap_id, sub_cap_name, category_id}, ...],
        "only_in_to":   [{sub_cap_id, sub_cap_name, category_id}, ...],
      }

    "Only in to" answers the operator's intent — subcaps that the
    comparison subvertical (`to`) is already practising but `from`
    hasn't tagged yet. That set is the expansion opportunity.
    """
    svs_by_code = {sv["code"]: sv for sv in _load_subverticals()}
    if from_code not in svs_by_code or to_code not in svs_by_code:
        return {
            "from": svs_by_code.get(from_code),
            "to": svs_by_code.get(to_code),
            "error": "unknown subvertical code",
            "common": [],
            "only_in_from": [],
            "only_in_to": [],
        }

    filt: dict = {}
    if pillar_id:
        filt["pillar_id"] = pillar_id

    from_mappings = {
        m["sub_cap_id"]
        for m in cat.list_vc_mappings({**filt, "subvertical_code": from_code})
        if m.get("stages")
    }
    to_mappings = {
        m["sub_cap_id"]
        for m in cat.list_vc_mappings({**filt, "subvertical_code": to_code})
        if m.get("stages")
    }
    subcap_index = {s["sub_cap_id"]: s for s in cat.list_subcaps(pillar_id)}

    def _enrich(sids: set[str]) -> list[dict]:
        out = []
        for sid in sorted(sids):
            sc = subcap_index.get(sid) or {}
            out.append({
                "sub_cap_id": sid,
                "sub_cap_name": sc.get("sub_cap_name") or sc.get("name"),
                "category_id": sc.get("category_id"),
                "l1_capability": sc.get("l1_capability"),
            })
        return out

    return {
        "from": {"code": from_code, "name": svs_by_code[from_code]["name"]},
        "to": {"code": to_code, "name": svs_by_code[to_code]["name"]},
        "common": sorted(from_mappings & to_mappings),
        "only_in_from": _enrich(from_mappings - to_mappings),
        "only_in_to": _enrich(to_mappings - from_mappings),
    }


# ─── Maturity Heatmap ────────────────────────────────────────────────────────


# ─── Maturity Heatmap ──────────────────────────────────────────────────────
#
# Each row is a subcap; cells are the five canonical M-bands (M1
# Foundational … M5 Transformational). For each row we now also compute:
#
#   * current_level  — the deepest M-band index that has a descriptor.
#                     Anchors the row's "you are here" tier.
#   * benchmark_level — the cohort median tier from benchmarks_service
#                      when a cohort is selected; null if no cohort data.
#   * gap            — current_level - benchmark_level (positive = ahead,
#                     negative = behind). Drives the "largest gap" sort.
#   * zds_band       — one of four ZDS marketing bands (activating /
#                     building / competing / differentiating). Mapped
#                     from current_level so the UI can colour-code with
#                     the canonical marketing palette.
#
# Cohort selection is best-effort: when `cohort_id` is passed but the
# cohort has no benchmark observations, we fall back to descriptor-only
# colouring and report `cohort_observations: 0` so the UI can warn.

_ZDS_BANDS = [
    None,                 # 0 (no descriptor at all)
    "activating",         # M1
    "building",           # M2
    "competing",          # M3
    "differentiating",    # M4
    "differentiating",    # M5 (top tier — same band, deepest level)
]


def _deepest_level(row: dict) -> int:
    """Return the deepest M-band index that has a non-empty descriptor,
    or 0 if none. Used as the row's `current_level`."""
    deepest = 0
    for i in range(1, 6):
        if row.get(f"m{i}"):
            deepest = i
    return deepest


def _zds_band_for(level: int) -> str | None:
    if level <= 0 or level > 5:
        return None
    return _ZDS_BANDS[level]


def _benchmark_levels_for_cohort(cohort_id: str | None) -> dict[str, int]:
    """For every subcap that has a benchmark distribution for the given
    cohort, return the median maturity tier (1–5).

    No-op when `cohort_id` is None or when benchmarks have no observations
    for the cohort. Implementation reuses the existing benchmarks
    repository — no new metrics computed here, just a lookup.
    """
    if not cohort_id:
        return {}
    from .repository import get_repository
    repo = get_repository()
    out: dict[str, int] = {}
    for dist in repo.list("benchmark_distributions"):
        if dist.get("cohort_id") != cohort_id:
            continue
        sid = dist.get("sub_cap_id")
        median = dist.get("median")
        if not sid or median is None:
            continue
        # Distribution medians are reported on 0–5 scale per benchmarks_service.
        try:
            lvl = max(1, min(5, int(round(float(median)))))
        except (TypeError, ValueError):
            continue
        out[sid] = lvl
    return out


def maturity_heatmap(
    pillar_id: str | None = None,
    cohort_id: str | None = None,
    sort: str = "category",
) -> dict:
    """Return rows × 5-band heatmap with ZDS band assignment + optional
    benchmark cohort overlay.

    Args:
        pillar_id:  filter to a single pillar (P1..P4).
        cohort_id:  optional benchmark cohort; rows get a `benchmark_level`
                    and `gap` derived from the cohort medians.
        sort:       "category" (default — pillar / category / l1 / id)
                    or "gap" (largest negative gap first → biggest
                    opportunities up top).
    """
    rows = cat.list_maturity({"pillar_id": pillar_id} if pillar_id else None)
    bench_levels = _benchmark_levels_for_cohort(cohort_id)

    levels = ["m1", "m2", "m3", "m4", "m5"]
    out_rows: list[dict] = []
    for r in rows:
        sid = r.get("sub_cap_id")
        current = _deepest_level(r)
        benchmark = bench_levels.get(sid) if cohort_id else None
        gap = (current - benchmark) if benchmark is not None else None
        out_rows.append({
            "sub_cap_id": sid,
            "sub_cap_name": r.get("sub_cap_name"),
            "category_id": r.get("category_id"),
            "l1_capability": r.get("l1_capability"),
            "current_level": current,
            "benchmark_level": benchmark,
            "gap": gap,
            "zds_band": _zds_band_for(current),
            "cells": [
                {
                    "level": lvl.upper(),
                    "filled": bool(r.get(lvl)),
                    "preview": (r.get(lvl) or "")[:140],
                }
                for lvl in levels
            ],
        })

    if sort == "gap" and cohort_id:
        # Negative gap = below benchmark = biggest opportunity. Stable by id.
        out_rows.sort(
            key=lambda x: (
                x.get("gap") if x.get("gap") is not None else 999,
                x.get("sub_cap_id") or "",
            )
        )
    else:
        out_rows.sort(
            key=lambda x: (
                x.get("category_id") or "",
                x.get("l1_capability") or "",
                x.get("sub_cap_id") or "",
            )
        )

    return {
        "pillar_id": pillar_id,
        "cohort_id": cohort_id,
        "cohort_observations": len(bench_levels),
        "sort": sort,
        "levels": [lvl.upper() for lvl in levels],
        "bands": [
            {"key": "activating", "label": "Activating", "tier_range": [1, 1]},
            {"key": "building", "label": "Building", "tier_range": [2, 2]},
            {"key": "competing", "label": "Competing", "tier_range": [3, 3]},
            {"key": "differentiating", "label": "Differentiating", "tier_range": [4, 5]},
        ],
        "rows": out_rows,
    }


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
