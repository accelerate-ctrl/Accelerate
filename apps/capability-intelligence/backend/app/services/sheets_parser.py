"""Parse a Pillar capability-map workbook (xlsx/xlsm) into normalized records.

Schema reference: Pillar 1 Capability Map v14.0 (sheet structure):
  1_Overview, 2_Capability_Map, 3_User_Stories_Catalogue, 4_L3_Detailed,
  5_L4_Detailed_Features, 6_Maturity_Descriptors, 15_Theme_SubCap_Mapping,
  21_VC_Mapping_PerSubcap, ...

We treat sheet `2_Capability_Map` as REQUIRED — its presence + correct header
row is what makes a workbook count as "complete" for ingestion. Other sheets
are best-effort: missing ones are flagged but ingestion proceeds.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

import openpyxl

from .ingestion.persona_parser import parse_personas

log = logging.getLogger(__name__)

REQUIRED_CAPMAP_HEADERS = [
    "Category",
    "L1_Capability",
    "Sub_Cap_ID",
    "Sub_Cap_Name",
]


@dataclass
class ParseResult:
    pillar_id: str
    pillar_name: str
    schema_status: str  # "complete" | "incomplete"
    schema_issues: list[str] = field(default_factory=list)

    pillars: list[dict] = field(default_factory=list)
    categories: list[dict] = field(default_factory=list)
    l1_capabilities: list[dict] = field(default_factory=list)
    subcaps: list[dict] = field(default_factory=list)
    use_cases: list[dict] = field(default_factory=list)
    l3_platforms: list[dict] = field(default_factory=list)
    l4_features: list[dict] = field(default_factory=list)
    maturity_descriptors: list[dict] = field(default_factory=list)
    theme_mappings: list[dict] = field(default_factory=list)
    stories: list[dict] = field(default_factory=list)
    vc_mappings: list[dict] = field(default_factory=list)

    # v7.0 schema extensions (Phase 1.3 — close QA_AUDIT F10 partially).
    # Each list maps 1:1 to a workbook tab and is persisted to its own
    # Firestore subcollection by ``catalogue_service._persist_pillar_slice``.
    agentforce_agents: list[dict] = field(default_factory=list)        # tab 8
    platform_constructs: list[dict] = field(default_factory=list)      # tab 9
    offerings: list[dict] = field(default_factory=list)                # tab 10
    data_products: list[dict] = field(default_factory=list)            # tab 11
    offering_subcap_matrix: list[dict] = field(default_factory=list)   # tab 12
    dataproduct_subcap_matrix: list[dict] = field(default_factory=list)  # tab 13
    cross_pillar_stories: list[dict] = field(default_factory=list)     # tab 14
    cross_pillar_coverage: list[dict] = field(default_factory=list)    # tab 16
    completeness: list[dict] = field(default_factory=list)             # tab 18
    cascade_simulation: list[dict] = field(default_factory=list)       # tab 19


# ─── Public API ──────────────────────────────────────────────────────────────


def parse_workbook(source: bytes | str | Path, default_pillar_id: str | None = None) -> ParseResult:
    """Parse a workbook from bytes or filesystem path.

    `default_pillar_id` is used if the workbook doesn't carry an explicit pillar
    code (we infer from `Sub_Cap_ID` prefixes when present).
    """
    if isinstance(source, (str, Path)):
        wb = openpyxl.load_workbook(source, read_only=True, data_only=True)
    else:
        wb = openpyxl.load_workbook(BytesIO(source), read_only=True, data_only=True)

    sheets = set(wb.sheetnames)
    issues: list[str] = []

    if "2_Capability_Map" not in sheets:
        return ParseResult(
            pillar_id=default_pillar_id or "P?",
            pillar_name=default_pillar_id or "Unknown",
            schema_status="incomplete",
            schema_issues=["missing sheet 2_Capability_Map"],
        )

    cap_rows, cap_headers = _read_sheet(wb["2_Capability_Map"])
    missing = [h for h in REQUIRED_CAPMAP_HEADERS if h not in cap_headers]
    if missing:
        issues.append(f"2_Capability_Map missing headers: {missing}")

    inferred_pillar_id = _infer_pillar_id(cap_rows, cap_headers, default_pillar_id)

    result = ParseResult(
        pillar_id=inferred_pillar_id,
        pillar_name=_pillar_name(inferred_pillar_id),
        schema_status="complete" if not issues else "incomplete",
        schema_issues=issues,
    )

    result.pillars.append({
        "pillar_id": inferred_pillar_id,
        "name": result.pillar_name,
        "schema_status": result.schema_status,
    })

    _emit_subcaps(cap_rows, cap_headers, result)
    if "6_Maturity_Descriptors" in sheets:
        _emit_maturity(*_read_sheet(wb["6_Maturity_Descriptors"]), result=result)
    if "4_L3_Detailed" in sheets:
        _emit_l3(*_read_sheet(wb["4_L3_Detailed"]), result=result)
    if "5_L4_Detailed_Features" in sheets:
        _emit_l4(*_read_sheet(wb["5_L4_Detailed_Features"]), result=result)
    if "15_Theme_SubCap_Mapping" in sheets:
        _emit_themes(*_read_sheet(wb["15_Theme_SubCap_Mapping"]), result=result)
    if "3_User_Stories_Catalogue" in sheets:
        _emit_stories(*_read_sheet(wb["3_User_Stories_Catalogue"]), result=result)
    if "21_VC_Mapping_PerSubcap" in sheets:
        _emit_vc_mappings(*_read_vc_sheet(wb["21_VC_Mapping_PerSubcap"]), result=result)

    # ── v7.0 extended tabs (Phase 1.3) ──
    if "8_Agentforce_Agents_List" in sheets:
        _emit_agentforce_agents(*_read_sheet(wb["8_Agentforce_Agents_List"]), result=result)
    if "9_Platform_Constructs_Library" in sheets:
        _emit_platform_constructs(*_read_sheet(wb["9_Platform_Constructs_Library"]), result=result)
    elif "9_Platform_Constructs" in sheets:
        _emit_platform_constructs(*_read_sheet(wb["9_Platform_Constructs"]), result=result)
    if "10_Productized_Offerings" in sheets:
        _emit_offerings(*_read_sheet(wb["10_Productized_Offerings"]), result=result)
    if "11_Data_Products" in sheets:
        _emit_data_products(*_read_sheet(wb["11_Data_Products"]), result=result)
    if "12_Offering_SubCap_Matrix" in sheets:
        _emit_offering_subcap_matrix(*_read_sheet(wb["12_Offering_SubCap_Matrix"]), result=result)
    if "13_DataProduct_SubCap_Matrix" in sheets:
        _emit_dataproduct_subcap_matrix(*_read_sheet(wb["13_DataProduct_SubCap_Matrix"]), result=result)
    if "14_CrossPillar_Stories" in sheets:
        _emit_cross_pillar_stories(*_read_sheet(wb["14_CrossPillar_Stories"]), result=result)
    if "16_SubCap_CrossPillar_Coverage" in sheets:
        _emit_cross_pillar_coverage(*_read_sheet(wb["16_SubCap_CrossPillar_Coverage"]), result=result)
    if "18_SubCap_Completeness_Profile" in sheets:
        _emit_completeness(*_read_sheet(wb["18_SubCap_Completeness_Profile"]), result=result)
    if "19_Toggle_Cascade_Simulation" in sheets:
        _emit_cascade_simulation(*_read_sheet(wb["19_Toggle_Cascade_Simulation"]), result=result)

    log.info(
        "parsed pillar=%s subcaps=%d l3=%d l4=%d maturity=%d themes=%d stories=%d "
        "agents=%d constructs=%d offerings=%d data_products=%d "
        "offering_matrix=%d dataproduct_matrix=%d xpillar_stories=%d "
        "coverage=%d completeness=%d cascade_sim=%d",
        result.pillar_id,
        len(result.subcaps),
        len(result.l3_platforms),
        len(result.l4_features),
        len(result.maturity_descriptors),
        len(result.theme_mappings),
        len(result.stories),
        len(result.agentforce_agents),
        len(result.platform_constructs),
        len(result.offerings),
        len(result.data_products),
        len(result.offering_subcap_matrix),
        len(result.dataproduct_subcap_matrix),
        len(result.cross_pillar_stories),
        len(result.cross_pillar_coverage),
        len(result.completeness),
        len(result.cascade_simulation),
    )
    return result


# ─── Internals ───────────────────────────────────────────────────────────────


def _read_sheet(ws) -> tuple[list[list[Any]], list[str]]:
    """Return (rows, headers). First non-empty row taken as headers."""
    rows = []
    headers: list[str] = []
    for r in ws.iter_rows(values_only=True):
        if not headers:
            if r and any(v is not None and str(v).strip() for v in r):
                headers = [str(v).strip() if v is not None else "" for v in r]
            continue
        # stop at first fully-empty row to avoid trailing thousands of blanks
        if r is None or all(v is None or (isinstance(v, str) and not v.strip()) for v in r):
            # don't stop entirely; some sheets have spacer rows. Just skip.
            continue
        rows.append(list(r))
    return rows, headers


def _infer_pillar_id(rows: list[list[Any]], headers: list[str], default: str | None) -> str:
    if "Sub_Cap_ID" in headers:
        idx = headers.index("Sub_Cap_ID")
        for r in rows[:50]:
            if r and len(r) > idx and r[idx]:
                m = re.match(r"^(P\d+)", str(r[idx]))
                if m:
                    return m.group(1)
    return default or "P?"


def _pillar_name(pillar_id: str) -> str:
    return {
        "P1": "Strategic Foundation, Governance & Culture",
        "P2": "Customer-Facing",
        "P3": "Operations & Risk",
        "P4": "Data, Analytics & AI",
    }.get(pillar_id, pillar_id)


def _row_dict(row: list[Any], headers: list[str]) -> dict[str, Any]:
    out = {}
    for i, h in enumerate(headers):
        if not h:
            continue
        if i < len(row):
            v = row[i]
            if isinstance(v, str):
                v = v.strip()
                if not v:
                    v = None
            out[h] = v
    return out


def _split_list(value: Any) -> list[str]:
    if value is None:
        return []
    s = str(value)
    parts = [p.strip() for p in re.split(r"[,;\n]", s) if p.strip()]
    return parts


def _emit_subcaps(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    seen_categories: dict[str, str] = {}  # cat_id -> name
    seen_l1: dict[tuple[str, str], None] = {}  # (cat_id, l1_name)

    for r in rows:
        d = _row_dict(r, headers)
        sub_cap_id = d.get("Sub_Cap_ID")
        if not sub_cap_id:
            continue
        category_id = d.get("Category")
        l1_name = d.get("L1_Capability")
        if category_id and category_id not in seen_categories:
            seen_categories[category_id] = l1_name or category_id
        key = (category_id or "", l1_name or "")
        if key not in seen_l1:
            seen_l1[key] = None
        # v7.0 personas: parse with paren-aware tokenizer so role
        # descriptions inside parens don't get shredded. ``personas``
        # keeps the denormalized canonical-name list (back-compat for
        # consumers that haven't migrated to structured PersonaRefs);
        # ``persona_refs`` carries the full structured payload.
        persona_refs = parse_personas(d.get("Personas"))
        result.subcaps.append({
            "sub_cap_id": sub_cap_id,
            "sub_cap_name": d.get("Sub_Cap_Name") or sub_cap_id,
            "pillar_id": result.pillar_id,
            "category_id": category_id or "",
            "l1_capability": l1_name or "",
            "description": d.get("Description"),
            "solution_type": d.get("Solution_Type"),
            "tier": d.get("Tier") or "T1",
            "personas": [ref.canonical_name for ref in persona_refs],
            "persona_refs": [ref.model_dump(by_alias=True) for ref in persona_refs],
            "l3_platforms": _split_list(d.get("L3_Platforms_Addressing_SubCap")),
            "l4_features": _split_list(d.get("L4_Features_Available")),
            "use_cases": _split_list(d.get("Use_Cases")),
            "story_refs": _split_list(d.get("Story_Refs_with_UC_Links")),
            "zennify_status": d.get("Zennify_Status"),
            # Lifecycle is computed by lifecycle_service from market
            # signals (PRD D4); ingest leaves it None and the service
            # writes it to the lifecycle_states/{sub_cap_id} document.
            "lifecycle_state": None,
        })

        # use cases — best-effort parse from the Use_Cases column
        for uc_str in _split_list(d.get("Use_Cases")):
            m = re.match(r"^(P\d+C\d+\.\d+\.\d+\.UC\d+)", uc_str)
            if m:
                uc_id = m.group(1)
                tag_match = re.search(r"\[([A-Z_]+)\]", uc_str)
                desc_match = re.search(r":\s*(.+)$", uc_str)
                result.use_cases.append({
                    "use_case_id": uc_id,
                    "sub_cap_id": sub_cap_id,
                    "label": tag_match.group(1) if tag_match else "",
                    "description": desc_match.group(1) if desc_match else None,
                })

    for cat_id, _ in seen_categories.items():
        result.categories.append({
            "category_id": cat_id,
            "pillar_id": result.pillar_id,
            "name": cat_id,
        })
    for cat_id, l1_name in seen_l1.keys():
        if not cat_id or not l1_name:
            continue
        l1_id = f"{cat_id}.{re.sub(r'[^A-Za-z0-9]+', '_', l1_name)}"
        result.l1_capabilities.append({
            "l1_id": l1_id,
            "category_id": cat_id,
            "pillar_id": result.pillar_id,
            "name": l1_name,
        })


def _emit_maturity(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    for r in rows:
        d = _row_dict(r, headers)
        sub_cap_id = d.get("Sub_Cap_ID")
        if not sub_cap_id:
            continue
        result.maturity_descriptors.append({
            "sub_cap_id": sub_cap_id,
            "sub_cap_name": d.get("Sub_Cap_Name") or sub_cap_id,
            "category_id": d.get("Category") or "",
            "l1_capability": d.get("L1_Capability") or "",
            "m1": d.get("M1_Foundational"),
            "m1_features": d.get("M1_Foundational_Features"),
            "m2": d.get("M2_Developing"),
            "m2_features": d.get("M2_Developing_Features"),
            "m3": d.get("M3_Established_AI_Assisted"),
            "m3_features": d.get("M3_Agentic_Features"),
            "m4": d.get("M4_Advanced_Hybrid_Agentic"),
            "m4_features": d.get("M4_Cross_System_Orchestration"),
            "m5": d.get("M5_Transformational_Headless360"),
            "m5_features": d.get("M5_Headless_360_Surfaces"),
        })


def _emit_l3(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    for r in rows:
        d = _row_dict(r, headers)
        l3_id = d.get("L3_ID")
        if not l3_id:
            continue
        result.l3_platforms.append({
            "l3_id": l3_id,
            "vendor": d.get("Vendor"),
            "name": d.get("Platform_Name") or l3_id,
            "category": d.get("Category"),
            "description": d.get("Description"),
            "detailed_capabilities": d.get("Detailed_Capabilities"),
            "setup_path": d.get("Setup_Path"),
            "prerequisites": d.get("Prerequisites"),
            "customization_extension_points": d.get("Customization_Extension_Points"),
            "common_combinations": d.get("Common_Combinations"),
            "pricing_tier_notes": d.get("Pricing_Tier_Notes"),
            "linked_l4_features": d.get("Linked_L4_Features"),
            "linked_sub_caps_top5": d.get("Linked_Sub_Caps_Top5"),
            "reference_url": d.get("Reference_URL"),
        })


def _emit_l4(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    for r in rows:
        d = _row_dict(r, headers)
        sub_cap_id = d.get("Sub_Cap_ID")
        feature_name = d.get("Feature_Name")
        if not sub_cap_id or not feature_name:
            continue
        result.l4_features.append({
            "sub_cap_id": sub_cap_id,
            "l3_platform_id": d.get("L3_Platform_ID"),
            "feature_name": feature_name,
            "vendor": d.get("Vendor"),
            "feature_type": d.get("Feature_Type"),
            "customization_level": d.get("Customization_Level"),
            "detailed_description": d.get("Detailed_Description"),
            "configuration_path": d.get("Configuration_Path"),
            "use_case_ids_using_feature": d.get("Use_Case_IDs_Using_Feature"),
            "reference_url": d.get("Reference_URL"),
        })


def _emit_themes(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    for r in rows:
        d = _row_dict(r, headers)
        theme = d.get("Theme")
        sub_cap_id = d.get("P1_Sub_Cap_ID") or d.get("Sub_Cap_ID")
        if not theme or not sub_cap_id:
            continue
        result.theme_mappings.append({
            "theme": theme,
            "sub_cap_id": sub_cap_id,
            "sub_cap_name": d.get("P1_Sub_Cap_Name") or d.get("Sub_Cap_Name"),
            "rationale": d.get("Mapping_Rationale (Customized - why cross-pillar)") or d.get("Mapping_Rationale"),
            "cross_pillar_story_count": d.get("Cross_Pillar_Story_Count_for_Theme"),
            "zennify_effective_status": d.get("Zennify_Effective_Status"),
        })


def _read_vc_sheet(ws) -> tuple[list[list[Any]], list[str]]:
    """The VC sheet has 3 banner rows above the real header.

    Find the row that begins with 'Category' and take it as headers; everything
    below is data.
    """
    headers: list[str] = []
    rows: list[list[Any]] = []
    for r in ws.iter_rows(values_only=True):
        if not headers:
            if r and r[0] and str(r[0]).strip().lower() == "category":
                headers = [str(v).strip() if v is not None else "" for v in r]
            continue
        if r is None:
            continue
        rows.append(list(r))
    return rows, headers


# Subvertical column-name → canonical code (loaded from config at module import).
def _load_subvertical_aliases() -> dict[str, str]:
    from pathlib import Path

    import yaml
    p = Path(__file__).resolve().parents[3] / "config" / "subverticals.yml"
    if not p.exists():
        return {}
    raw = yaml.safe_load(p.read_text())
    out: dict[str, str] = {}
    for sv in raw.get("subverticals", []):
        for alias in sv.get("column_aliases", []) + [sv["name"], sv["code"]]:
            out[alias.strip().lower()] = sv["code"]
    return out


_SUBVERTICAL_ALIASES = _load_subvertical_aliases()


def _split_stages(cell: Any) -> list[str]:
    """VC cells are encoded as `▌ STAGE A\n▌ STAGE B`. Split on the marker."""
    if cell is None:
        return []
    s = str(cell).strip()
    parts = [p.strip(" \t▌") for p in s.split("▌")]
    return [p for p in parts if p]


def _emit_vc_mappings(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    if "Sub_Cap_ID" not in headers:
        return
    sub_idx = headers.index("Sub_Cap_ID")
    # Map subvertical-column-index → canonical code (e.g., RB)
    col_to_code: dict[int, str] = {}
    for i, h in enumerate(headers):
        code = _SUBVERTICAL_ALIASES.get((h or "").strip().lower())
        if code:
            col_to_code[i] = code

    for r in rows:
        if not r or len(r) <= sub_idx:
            continue
        sub_cap_id = r[sub_idx]
        if not sub_cap_id:
            continue
        for col, code in col_to_code.items():
            if col >= len(r):
                continue
            stages = _split_stages(r[col])
            if not stages:
                continue
            result.vc_mappings.append({
                "sub_cap_id": str(sub_cap_id),
                "subvertical_code": code,
                "stages": stages,
            })


def _emit_stories(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    for r in rows:
        d = _row_dict(r, headers)
        story_key = d.get("Story_Key")
        if not story_key:
            continue
        result.stories.append({
            "story_key": story_key,
            "source_type": d.get("Source_Type"),
            "source_ref": d.get("Source_Ref"),
            "sub_cap_id": d.get("Sub_Cap_ID"),
            "sub_cap_name": d.get("Sub_Cap_Name"),
            "use_case_ids": _split_list(d.get("Use_Case_IDs")),
            "match_confidence": d.get("Match_Confidence"),
            "summary": d.get("Story_Summary"),
        })


# ─── v7.0 extended emitters (Phase 1.3) ──────────────────────────────────────
#
# Each emitter is small + defensive: it skips rows missing the primary key,
# tolerates header variants the workbook authors used over different
# revisions, and normalises numeric counts to int when possible. Nothing
# fails the parse — bad rows just get skipped and the row count comes out
# lower than expected, which surfaces as a schema_status anomaly in
# Mission Control.


def _to_int(value: Any) -> int | None:
    """Coerce a workbook cell to int, returning None for blanks / NaN."""
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _emit_agentforce_agents(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    """Tab 8 — Agentforce_Agents_List."""
    for r in rows:
        d = _row_dict(r, headers)
        agent_id = d.get("Agent_ID")
        if not agent_id:
            continue
        result.agentforce_agents.append({
            "agent_id": agent_id,
            "pillar_id": result.pillar_id,
            "agent_name": d.get("Agent_Name"),
            "lob": d.get("LOB"),
            "workflow": d.get("Workflow"),
            "status": d.get("Status"),
            "source_type": d.get("Source_Type"),
            "parent_l3": d.get("Parent_L3"),
            "description": d.get("Description"),
            "source_url": d.get("Source_URL"),
        })


def _emit_platform_constructs(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    """Tab 9 — Platform_Constructs_Library."""
    for r in rows:
        d = _row_dict(r, headers)
        name = d.get("Construct_Name")
        if not name:
            continue
        result.platform_constructs.append({
            "construct_name": name,
            "pillar_id": result.pillar_id,
            "vendor": d.get("Vendor"),
            "description": d.get("Description"),
            "syntax_hint": d.get("Syntax_Hint"),
            "docs_url": d.get("Docs_URL"),
        })


def _emit_offerings(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    """Tab 10 — Productized_Offerings.

    Note: v7.0 offerings are cross-pillar by design (same OFF-* id may
    appear in P1 and P3 workbooks). The cross-pillar dedup happens at
    persist time in ``canonical_entity_service`` (Phase 1.4); the
    parser keeps the full row from this pillar's workbook.
    """
    for r in rows:
        d = _row_dict(r, headers)
        oid = d.get("Offering_ID")
        if not oid:
            continue
        result.offerings.append({
            "offering_id": oid,
            "source_pillar_id": result.pillar_id,
            "offering_name": d.get("Offering_Name"),
            "category": d.get("Category"),
            "wrap_around": d.get("Wrap_Around"),
            "status": d.get("Status"),
            "overview": d.get("Overview"),
            "industry_challenge": d.get("Industry_Challenge"),
            "outcomes": d.get("Outcomes (semicolon-separated)"),
            "core_capabilities": d.get("Core_Capabilities (capability: description)"),
            "tiers": d.get("Tiers (tier - pricing - description)"),
            "primary_vendors": d.get("Primary_Vendors"),
            "l3_platforms_used": _split_list(d.get("L3_Platforms_Used")),
            "target_personas": _split_list(d.get("Target_Personas")),
            "reference_url": d.get("Reference_URL"),
            "source_evidence": d.get("Source_Evidence"),
            "source_doc_section": d.get("Source_Doc_Section"),
            "total_mapped_subcaps": _to_int(d.get("Total_Mapped_SubCaps")),
            "active_mapped_subcaps": _to_int(d.get("Active_Mapped_SubCaps")),
            "linkage_health_pct": _to_float(d.get("Linkage_Health_Pct")),
            "zennify_effective_status": d.get("Zennify_Effective_Status"),
        })


def _emit_data_products(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    """Tab 11 — Data_Products."""
    for r in rows:
        d = _row_dict(r, headers)
        mid = d.get("Module_ID")
        if not mid:
            continue
        result.data_products.append({
            "module_id": mid,
            "source_pillar_id": result.pillar_id,
            "module_name": d.get("Module_Name"),
            "category": d.get("Category"),
            "description": d.get("Description"),
            "typical_pairing": d.get("Typical_Pairing (Offerings)"),
            "validation_strength": d.get("Validation_Strength"),
            "reference_url": d.get("Reference_URL"),
            "source_doc_section": d.get("Source_Doc_Section"),
            "total_mapped_subcaps": _to_int(d.get("Total_Mapped_SubCaps")),
            "active_mapped_subcaps": _to_int(d.get("Active_Mapped_SubCaps")),
            "linkage_health_pct": _to_float(d.get("Linkage_Health_Pct")),
            "zennify_effective_status": d.get("Zennify_Effective_Status"),
        })


def _emit_offering_subcap_matrix(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    """Tab 12 — Offering_SubCap_Matrix."""
    for r in rows:
        d = _row_dict(r, headers)
        oid = d.get("Offering_ID")
        sc = d.get("Sub_Cap_ID")
        if not oid or not sc:
            continue
        result.offering_subcap_matrix.append({
            "offering_id": oid,
            "sub_cap_id": sc,
            "pillar_id": result.pillar_id,
            "offering_name": d.get("Offering_Name"),
            "sub_cap_name": d.get("Sub_Cap_Name"),
            "mapping_rationale": d.get(
                "Mapping_Rationale (Customized - WHY this offering directly addresses this sub-cap)"
            ) or d.get("Mapping_Rationale"),
            "maturity_lift": d.get("Maturity_Lift (Current State → Target State)") or d.get("Maturity_Lift"),
            "capabilities_addressing_subcap": d.get("Capabilities_Addressing_SubCap"),
            "reference_url": d.get("Reference_URL"),
            "zennify_effective_status": d.get("Zennify_Effective_Status"),
        })


def _emit_dataproduct_subcap_matrix(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    """Tab 13 — DataProduct_SubCap_Matrix."""
    for r in rows:
        d = _row_dict(r, headers)
        mid = d.get("Module_ID")
        sc = d.get("Sub_Cap_ID")
        if not mid or not sc:
            continue
        result.dataproduct_subcap_matrix.append({
            "module_id": mid,
            "sub_cap_id": sc,
            "pillar_id": result.pillar_id,
            "module_name": d.get("Module_Name"),
            "sub_cap_name": d.get("Sub_Cap_Name"),
            "mapping_rationale": d.get("Mapping_Rationale (Customized)") or d.get("Mapping_Rationale"),
            "maturity_lift": d.get("Maturity_Lift (Current State → Target State)") or d.get("Maturity_Lift"),
            "reference_url": d.get("Reference_URL"),
            "zennify_effective_status": d.get("Zennify_Effective_Status"),
        })


def _emit_cross_pillar_stories(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    """Tab 14 — CrossPillar_Stories.

    Each row is a generated story originating in another pillar that
    touches this pillar's subcaps. The 3-state cascade column (Active /
    Partial / Inactive) is the ``zennify_effective_status`` field.
    """
    for r in rows:
        d = _row_dict(r, headers)
        key = d.get("Story_Key")
        if not key:
            continue
        result.cross_pillar_stories.append({
            "story_key": key,
            "destination_pillar_id": result.pillar_id,
            "origin_pillar": d.get("Origin_Pillar"),
            "origin_pillar_name": d.get("Origin_Pillar_Name"),
            "origin_sub_cap_id": d.get("Origin_SubCap_ID"),
            "origin_sub_cap_name": d.get("Origin_SubCap_Name"),
            "origin_l1_capability": d.get("Origin_L1_Capability"),
            "themes": [t.strip() for t in str(d.get("P1_Themes") or d.get("Themes") or "").split(";") if t.strip()],
            "theme_count": _to_int(d.get("Theme_Count")),
            "confidence_level": d.get("Confidence_Level"),
            "story_title": d.get("Story_Title"),
            "story_summary": d.get("Story_Summary"),
            "linked_sub_caps": [
                s.strip()
                for s in str(d.get("Linked_P1_SubCaps") or d.get("Linked_SubCaps") or "").split(";")
                if s.strip()
            ],
            "linked_sub_cap_count": _to_int(d.get("Linked_SubCap_Count")),
            "linked_offerings": d.get("Linked_Offerings"),
            "linked_offering_count": _to_int(d.get("Linked_Offering_Count")),
            "source_reference": d.get("Source_Reference"),
            "active_linked_sub_cap_count": _to_int(d.get("Active_Linked_SubCap_Count")),
            "zennify_effective_status": d.get("Zennify_Effective_Status"),
        })


def _emit_cross_pillar_coverage(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    """Tab 16 — SubCap_CrossPillar_Coverage.

    Aggregates how many cross-pillar stories touch each subcap, broken
    down by source pillar. Drives the Subcap Deep Dive cross-pillar
    section + Mission Control density matrix.
    """
    for r in rows:
        d = _row_dict(r, headers)
        sc = d.get("P1_Sub_Cap_ID") or d.get("Sub_Cap_ID")
        if not sc:
            continue
        result.cross_pillar_coverage.append({
            "sub_cap_id": sc,
            "pillar_id": result.pillar_id,
            "sub_cap_name": d.get("P1_Sub_Cap_Name") or d.get("Sub_Cap_Name"),
            "total_cross_pillar_stories": _to_int(d.get("Total_Cross_Pillar_Stories")),
            "p2_stories": _to_int(d.get("P2_Stories")),
            "p3_stories": _to_int(d.get("P3_Stories")),
            "p4_stories": _to_int(d.get("P4_Stories")),
            "themes_contributing": [
                t.strip()
                for t in str(d.get("Themes_Contributing") or "").split(";")
                if t.strip()
            ],
            "linked_offerings_strict": d.get("Linked_Offerings (Strict - from Batch 3 Mapping)"),
            "top_story_examples": d.get("Top_Story_Examples (key | title excerpt)"),
            "zennify_effective_status": d.get("Zennify_Effective_Status"),
        })


def _emit_completeness(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    """Tab 18 — SubCap_Completeness_Profile.

    The authoritative completeness score per subcap (5 core layers + 3
    extended layers = max 8). Replaces today's computed completeness on
    Subcap Deep Dive with the workbook-curated version.
    """
    for r in rows:
        d = _row_dict(r, headers)
        sc = d.get("Sub_Cap_ID")
        if not sc:
            continue
        result.completeness.append({
            "sub_cap_id": sc,
            "pillar_id": result.pillar_id,
            "sub_cap_name": d.get("Sub_Cap_Name"),
            "category_id": d.get("Category"),
            "l1_capability": d.get("L1_Capability"),
            "stories_count": _to_int(d.get("Stories_Count")),
            "l4_count": _to_int(d.get("L4_Count")),
            "maturity_count": _to_int(d.get("Maturity_Count")),
            "l3_count": _to_int(d.get("L3_Count")),
            "use_case_count": _to_int(d.get("UseCase_Count")),
            "offering_count": _to_int(d.get("Offering_Count")),
            "mapped_offerings": d.get("Mapped_Offerings"),
            "data_product_count": _to_int(d.get("DataProduct_Count")),
            "mapped_data_products": d.get("Mapped_DataProducts"),
            "theme": d.get("Theme"),
            "cross_pillar_stories": _to_int(d.get("CrossPillar_Stories")),
            "core_score": _to_int(d.get("Core_Score (max 5)")),
            "extended_score": _to_int(d.get("Extended_Score (max 3)")),
            "total_score": _to_int(d.get("Total_Score (max 8)")),
            "narrative": d.get("Customized_Completeness_Narrative"),
            "zennify_effective_status": d.get("Zennify_Effective_Status"),
        })


def _emit_cascade_simulation(rows: list[list[Any]], headers: list[str], result: ParseResult) -> None:
    """Tab 19 — Toggle_Cascade_Simulation.

    Pre-computed cascade impact estimates per subcap. The
    :mod:`cascade_service` produces these dynamically at runtime; this
    table is the workbook author's static reference, useful for
    audit-trail reconciliation.
    """
    for r in rows:
        d = _row_dict(r, headers)
        sc = d.get("Sub_Cap_ID")
        if not sc:
            continue
        result.cascade_simulation.append({
            "sub_cap_id": sc,
            "pillar_id": result.pillar_id,
            "sub_cap_name": d.get("Sub_Cap_Name"),
            "direct_stories_inactive": _to_int(d.get("→User_Stories_Inactive")),
            "direct_l4_features_inactive": _to_int(d.get("→L4_Features_Inactive")),
            "direct_maturity_inactive": _to_int(d.get("→Maturity_Rows_Inactive")),
            "direct_l3_affected": _to_int(d.get("→L3_References_Affected")),
            "direct_offerings_inactive": _to_int(d.get("→Offering_Mappings_Inactive")),
            "direct_data_products_inactive": _to_int(d.get("→DataProduct_Mappings_Inactive")),
            "direct_themes_inactive": _to_int(d.get("→Theme_Mappings_Inactive")),
            "direct_coverage_inactive": _to_int(d.get("→Coverage_Rows_Inactive")),
            "indirect_xpillar_partial": _to_int(d.get("→Cross_Pillar_Stories_Going_Partial")),
            "indirect_xpillar_inactive": _to_int(d.get("→Cross_Pillar_Stories_Going_Inactive")),
            "indirect_offerings_partial": _to_int(d.get("→Offerings_Going_Partial")),
            "indirect_data_products_partial": _to_int(d.get("→DataProducts_Going_Partial")),
            "total_cascade_footprint": _to_int(d.get("Total_Cascade_Footprint")),
            "cascade_severity": d.get("Cascade_Severity"),
            "zennify_effective_status": d.get("Zennify_Effective_Status"),
        })
