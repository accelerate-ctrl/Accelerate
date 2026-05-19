"""Catalogue ingestion + read facade. Coordinates Drive -> parser -> repo."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from .drive_service import CatalogueFile, download_file, list_pillar_files
from .repository import Repository, get_repository
from .sheets_parser import ParseResult, parse_workbook

log = logging.getLogger(__name__)


COLLECTIONS = {
    "pillars": "pillars",
    "categories": "categories",
    "l1": "l1_capabilities",
    "subcaps": "subcaps",
    "use_cases": "use_cases",
    "l3": "l3_platforms",
    "l4": "l4_features",
    "maturity": "maturity_descriptors",
    "themes": "theme_mappings",
    "stories": "stories",
    "vc_mappings": "vc_mappings",
    "ingest_runs": "ingest_runs",
    "flags": "flags",
    "settings": "settings",
    # v7.0 extended (Phase 1.3) — closes part of QA_AUDIT F10. Each
    # collection mirrors a workbook tab so the catalogue surface can
    # join them back to subcaps for the Subcap Deep Dive (17 sections)
    # and the Vendor / Use-Case / Cross-Pillar pages.
    "agentforce_agents": "agentforce_agents",
    "platform_constructs": "platform_constructs",
    "offerings": "offerings",
    "data_products": "data_products",
    "offering_subcap_matrix": "offering_subcap_matrix",
    "dataproduct_subcap_matrix": "dataproduct_subcap_matrix",
    "cross_pillar_stories": "cross_pillar_stories",
    "cross_pillar_coverage": "cross_pillar_coverage",
    "completeness": "completeness",
    "cascade_simulation": "cascade_simulation",
}


@dataclass
class IngestRunResult:
    run_id: str
    started_at: datetime
    completed_at: datetime
    pillars_attempted: list[str]
    pillars_loaded: list[str]
    pillars_skipped: list[dict]  # [{pillar_id, reason}]
    counts_by_pillar: dict[str, dict[str, int]]
    flags_raised: list[dict]


# ─── Discovery / refresh API ─────────────────────────────────────────────────


def discover_pillar_files() -> dict[str, CatalogueFile]:
    """Light-weight directory scan; no parsing."""
    return list_pillar_files()


def refresh_pillar(pillar_id: str, *, by: str = "system") -> IngestRunResult:
    """Refresh a single pillar (re-pick latest file, parse, persist)."""
    return _run_ingest(by=by, pillar_filter=pillar_id)


def refresh_all_pillars(*, by: str = "system") -> IngestRunResult:
    return _run_ingest(by=by, pillar_filter=None)


def ingest_uploaded_workbook(
    *,
    pillar_id: str,
    file_name: str,
    content: bytes,
    by: str = "system",
) -> IngestRunResult:
    """Parse + persist a workbook uploaded directly from the SPA.

    Bypasses Drive discovery — used by `POST /api/sheets/upload` so pillar
    leads can ship pending-approval v7.0 workbooks without a Drive round-trip.
    Same persistence path as the scheduled refresh, so D21 (global catalogue
    state) is honoured.
    """
    started = datetime.utcnow()
    repo = get_repository()
    loaded: list[str] = []
    skipped: list[dict] = []
    counts: dict[str, dict[str, int]] = {}
    flags: list[dict] = []

    try:
        result = parse_workbook(content, default_pillar_id=pillar_id)
    except Exception as e:
        log.exception("upload parse failed for %s", pillar_id)
        flag = _make_flag(
            "INGEST_FAILURE", "HIGH", "pillar", pillar_id,
            f"Failed to parse uploaded {file_name}", str(e),
        )
        flags.append(flag)
        repo.upsert(COLLECTIONS["flags"], flag["flag_id"], flag)
        skipped.append({"pillar_id": pillar_id, "reason": "parse_failure"})
    else:
        if result.schema_status != "complete":
            flag = _make_flag(
                "SCHEMA_INCOMPLETE", "HIGH", "pillar", pillar_id,
                f"{file_name}: schema not aligned with v7.0 reference",
                "; ".join(result.schema_issues or ["unknown"]),
                extra={"file": file_name, "issues": result.schema_issues},
            )
            flags.append(flag)
            repo.upsert(COLLECTIONS["flags"], flag["flag_id"], flag)

        pillar_doc = (result.pillars[0] if result.pillars else {
            "pillar_id": pillar_id, "name": pillar_id, "schema_status": result.schema_status,
        })
        pillar_doc.update({
            "source_file_id": f"upload:{file_name}",
            "source_file_name": file_name,
            "source_file_modified_at": started.isoformat(),
            "source_version": f"upload-{int(started.timestamp())}",
            "schema_status": result.schema_status,
            "ingested_at": started.isoformat(),
            "ingested_by": by,
        })
        repo.upsert(COLLECTIONS["pillars"], pillar_id, pillar_doc)
        _persist_pillar_slice(repo, pillar_id, result)
        loaded.append(pillar_id)
        counts[pillar_id] = {
            "categories": len(result.categories),
            "l1": len(result.l1_capabilities),
            "subcaps": len(result.subcaps),
            "use_cases": len(result.use_cases),
            "l3": len(result.l3_platforms),
            "l4": len(result.l4_features),
            "maturity": len(result.maturity_descriptors),
            "themes": len(result.theme_mappings),
            "stories": len(result.stories),
            "vc_mappings": len(result.vc_mappings),
        }

    try:
        from . import graph_service
        graph_service.invalidate_cache()
    except Exception:
        pass

    completed = datetime.utcnow()
    run_id = f"upload-{pillar_id}-{int(started.timestamp())}"
    run_doc = {
        "run_id": run_id,
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "by": by,
        "source": "manual_upload",
        "file_name": file_name,
        "pillars_attempted": [pillar_id],
        "pillars_loaded": loaded,
        "pillars_skipped": skipped,
        "counts_by_pillar": counts,
        "flags_raised": [f["flag_id"] for f in flags],
    }
    repo.upsert(COLLECTIONS["ingest_runs"], run_id, run_doc)

    return IngestRunResult(
        run_id=run_id,
        started_at=started,
        completed_at=completed,
        pillars_attempted=[pillar_id],
        pillars_loaded=loaded,
        pillars_skipped=skipped,
        counts_by_pillar=counts,
        flags_raised=flags,
    )


def _run_ingest(*, by: str, pillar_filter: str | None) -> IngestRunResult:
    started = datetime.utcnow()
    repo = get_repository()
    files = discover_pillar_files()
    if pillar_filter:
        files = {pid: f for pid, f in files.items() if pid == pillar_filter}

    attempted: list[str] = sorted(files.keys()) if files else ([pillar_filter] if pillar_filter else [])
    loaded: list[str] = []
    skipped: list[dict] = []
    counts: dict[str, dict[str, int]] = {}
    flags: list[dict] = []

    if not files:
        skipped.append({"pillar_id": pillar_filter or "*", "reason": "no files discovered"})

    for pid, f in files.items():
        try:
            content = download_file(f)
            result = parse_workbook(content, default_pillar_id=pid)
        except Exception as e:
            log.exception("ingest failed for %s", pid)
            flag = _make_flag("INGEST_FAILURE", "HIGH", "pillar", pid, f"Failed to ingest {f.file_name}", str(e))
            flags.append(flag)
            repo.upsert(COLLECTIONS["flags"], flag["flag_id"], flag)
            skipped.append({"pillar_id": pid, "reason": "ingest_failure"})
            continue

        if result.schema_status != "complete":
            flag = _make_flag(
                "SCHEMA_INCOMPLETE", "HIGH", "pillar", pid,
                f"{f.file_name}: schema not aligned with Pillar 1 reference",
                "; ".join(result.schema_issues or ["unknown"]),
                extra={"file": f.file_name, "issues": result.schema_issues},
            )
            flags.append(flag)
            repo.upsert(COLLECTIONS["flags"], flag["flag_id"], flag)
            # Still persist what we have (the pillar doc and any parsed rows)
            # so the user can see the file showed up.

        # Persist Pillar doc with provenance
        pillar_doc = (result.pillars[0] if result.pillars else {"pillar_id": pid, "name": pid, "schema_status": result.schema_status})
        pillar_doc.update({
            "source_file_id": f.file_id,
            "source_file_name": f.file_name,
            "source_file_modified_at": f.modified_at.isoformat() if isinstance(f.modified_at, datetime) else str(f.modified_at),
            "source_version": f.parsed_version,
            "schema_status": result.schema_status,
            "ingested_at": started.isoformat(),
        })
        repo.upsert(COLLECTIONS["pillars"], pid, pillar_doc)

        # Replace this pillar's slice of each child collection
        _persist_pillar_slice(repo, pid, result)

        loaded.append(pid)
        counts[pid] = {
            "categories": len(result.categories),
            "l1": len(result.l1_capabilities),
            "subcaps": len(result.subcaps),
            "use_cases": len(result.use_cases),
            "l3": len(result.l3_platforms),
            "l4": len(result.l4_features),
            "maturity": len(result.maturity_descriptors),
            "themes": len(result.theme_mappings),
            "stories": len(result.stories),
            "vc_mappings": len(result.vc_mappings),
        }

    # Invalidate downstream caches that derive from catalogue contents.
    try:
        from . import graph_service
        graph_service.invalidate_cache()
    except Exception:  # graph_service depends on networkx; absent in some test paths
        pass

    # Rebuild the cross-pillar canonical entities (Phase 1.4) so the
    # Offering / DataProduct / L3 dedup view stays consistent with the
    # per-pillar ingest. Wrapped in try/except so an ingest never fails
    # solely because canonicalisation hit an edge case.
    if loaded:
        try:
            from . import canonical_entity_service
            canonical_entity_service.rebuild_canonical_entities()
        except Exception:
            log.exception("canonical-entity rebuild failed; ingest succeeded")

    completed = datetime.utcnow()
    run_id = f"ingest-{int(started.timestamp())}"
    run_doc = {
        "run_id": run_id,
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "by": by,
        "pillars_attempted": attempted,
        "pillars_loaded": loaded,
        "pillars_skipped": skipped,
        "counts_by_pillar": counts,
        "flags_raised": [f["flag_id"] for f in flags],
    }
    repo.upsert(COLLECTIONS["ingest_runs"], run_id, run_doc)

    return IngestRunResult(
        run_id=run_id,
        started_at=started,
        completed_at=completed,
        pillars_attempted=attempted,
        pillars_loaded=loaded,
        pillars_skipped=skipped,
        counts_by_pillar=counts,
        flags_raised=flags,
    )


def _persist_pillar_slice(repo: Repository, pid: str, result: ParseResult) -> None:
    """Replace this pillar's rows in each child collection (atomic-ish per coll).

    Wrapped in ``defer_persist`` so the ~10k cross-pillar stories +
    cascade rows don't generate a disk flush per row. Without this the
    P1 refresh balloons from ~5s to >2 minutes purely on the
    delete-then-insert loop.
    """
    with repo.defer_persist():
        _persist_pillar_slice_inner(repo, pid, result)


def _persist_pillar_slice_inner(repo: Repository, pid: str, result: ParseResult) -> None:
    # Load existing rows for the pillar, delete, then insert.
    for coll_key, items in (
        ("categories", result.categories),
        ("l1", result.l1_capabilities),
        ("subcaps", result.subcaps),
        ("use_cases", result.use_cases),
        ("maturity", result.maturity_descriptors),
        ("themes", result.theme_mappings),
        ("stories", result.stories),
        ("vc_mappings", result.vc_mappings),
        # v7.0 extended slices (Phase 1.3).
        ("agentforce_agents", result.agentforce_agents),
        ("platform_constructs", result.platform_constructs),
        ("offerings", result.offerings),
        ("data_products", result.data_products),
        ("offering_subcap_matrix", result.offering_subcap_matrix),
        ("dataproduct_subcap_matrix", result.dataproduct_subcap_matrix),
        ("cross_pillar_stories", result.cross_pillar_stories),
        ("cross_pillar_coverage", result.cross_pillar_coverage),
        ("completeness", result.completeness),
        ("cascade_simulation", result.cascade_simulation),
    ):
        coll = COLLECTIONS[coll_key]
        # Drop existing pillar slice
        for old in repo.list(coll, {"pillar_id": pid}):
            doc_id = _doc_id_for(coll_key, old)
            if doc_id:
                repo.delete(coll, doc_id)
        # Insert new
        upserts = []
        for item in items:
            item_doc = dict(item)
            item_doc.setdefault("pillar_id", pid)
            doc_id = _doc_id_for(coll_key, item_doc)
            if doc_id:
                upserts.append((doc_id, item_doc))
        if upserts:
            repo.upsert_many(coll, upserts)

    # L3 & L4 are not strictly per-pillar, but we tag with the source pillar.
    for coll_key, items in (("l3", result.l3_platforms), ("l4", result.l4_features)):
        coll = COLLECTIONS[coll_key]
        upserts = []
        for item in items:
            item_doc = dict(item)
            item_doc.setdefault("source_pillar_id", pid)
            doc_id = _doc_id_for(coll_key, item_doc)
            if doc_id:
                upserts.append((doc_id, item_doc))
        if upserts:
            repo.upsert_many(coll, upserts)


def _doc_id_for(coll_key: str, doc: dict) -> str | None:
    if coll_key in ("categories",):
        return doc.get("category_id")
    if coll_key == "l1":
        return doc.get("l1_id")
    if coll_key in ("subcaps", "maturity"):
        return doc.get("sub_cap_id")
    if coll_key == "use_cases":
        return doc.get("use_case_id")
    if coll_key == "l3":
        return doc.get("l3_id")
    if coll_key == "l4":
        sub = doc.get("sub_cap_id") or ""
        feat = doc.get("feature_name") or ""
        plat = doc.get("l3_platform_id") or ""
        return f"{sub}::{plat}::{feat}"
    if coll_key == "themes":
        return f"{doc.get('theme')}::{doc.get('sub_cap_id')}"
    if coll_key == "stories":
        return doc.get("story_key")
    if coll_key == "vc_mappings":
        return f"{doc.get('sub_cap_id')}::{doc.get('subvertical_code')}"
    # v7.0 extended ids (Phase 1.3) — composite keys keep cross-pillar
    # rows distinct when the same Offering / DataProduct appears in
    # multiple pillar workbooks.
    if coll_key == "agentforce_agents":
        return doc.get("agent_id")
    if coll_key == "platform_constructs":
        return f"{doc.get('vendor') or '?'}::{doc.get('construct_name')}"
    if coll_key == "offerings":
        return f"{doc.get('source_pillar_id') or doc.get('pillar_id') or '?'}::{doc.get('offering_id')}"
    if coll_key == "data_products":
        return f"{doc.get('source_pillar_id') or doc.get('pillar_id') or '?'}::{doc.get('module_id')}"
    if coll_key == "offering_subcap_matrix":
        return f"{doc.get('offering_id')}::{doc.get('sub_cap_id')}"
    if coll_key == "dataproduct_subcap_matrix":
        return f"{doc.get('module_id')}::{doc.get('sub_cap_id')}"
    if coll_key == "cross_pillar_stories":
        # Destination pillar disambiguates the same Story_Key landing in
        # different pillar workbooks.
        return f"{doc.get('destination_pillar_id') or doc.get('pillar_id') or '?'}::{doc.get('story_key')}"
    if coll_key in ("cross_pillar_coverage", "completeness", "cascade_simulation"):
        return doc.get("sub_cap_id")
    return None


def _make_flag(kind: str, severity: str, target_type: str, target_id: str, title: str, detail: str, extra: dict | None = None) -> dict:
    now = datetime.utcnow()
    return {
        "flag_id": f"flag-{kind.lower()}-{target_id}-{int(now.timestamp())}",
        "kind": kind,
        "severity": severity,
        "target_type": target_type,
        "target_id": target_id,
        "title": title,
        "detail": detail,
        "detected_at": now.isoformat(),
        "detected_by": "system",
        "resolved_at": None,
        "resolved_by": None,
        "resolution_note": None,
        "extra": extra or {},
    }


# ─── Read API ────────────────────────────────────────────────────────────────


def list_pillars() -> list[dict]:
    return get_repository().list(COLLECTIONS["pillars"])


def list_categories(pillar_id: str | None = None) -> list[dict]:
    flt = {"pillar_id": pillar_id} if pillar_id else None
    return get_repository().list(COLLECTIONS["categories"], flt)


def list_subcaps(pillar_id: str | None = None) -> list[dict]:
    flt = {"pillar_id": pillar_id} if pillar_id else None
    return get_repository().list(COLLECTIONS["subcaps"], flt)


def get_subcap(sub_cap_id: str) -> dict | None:
    return get_repository().get(COLLECTIONS["subcaps"], sub_cap_id)


def get_maturity(sub_cap_id: str) -> dict | None:
    return get_repository().get(COLLECTIONS["maturity"], sub_cap_id)


def list_l3() -> list[dict]:
    return get_repository().list(COLLECTIONS["l3"])


def list_l4(filter: dict | None = None) -> list[dict]:
    return get_repository().list(COLLECTIONS["l4"], filter)


def list_use_cases(filter: dict | None = None) -> list[dict]:
    return get_repository().list(COLLECTIONS["use_cases"], filter)


def list_themes(filter: dict | None = None) -> list[dict]:
    return get_repository().list(COLLECTIONS["themes"], filter)


def list_maturity(filter: dict | None = None) -> list[dict]:
    return get_repository().list(COLLECTIONS["maturity"], filter)


def list_vc_mappings(filter: dict | None = None) -> list[dict]:
    return get_repository().list(COLLECTIONS["vc_mappings"], filter)


def list_l1(filter: dict | None = None) -> list[dict]:
    return get_repository().list(COLLECTIONS["l1"], filter)


def list_l4_for(sub_cap_id: str) -> list[dict]:
    return get_repository().list(COLLECTIONS["l4"], {"sub_cap_id": sub_cap_id})


def list_use_cases_for(sub_cap_id: str) -> list[dict]:
    return get_repository().list(COLLECTIONS["use_cases"], {"sub_cap_id": sub_cap_id})


def list_themes_for(sub_cap_id: str) -> list[dict]:
    return get_repository().list(COLLECTIONS["themes"], {"sub_cap_id": sub_cap_id})


def list_stories_for(sub_cap_id: str) -> list[dict]:
    return get_repository().list(COLLECTIONS["stories"], {"sub_cap_id": sub_cap_id})


def list_flags(open_only: bool = True) -> list[dict]:
    flags = get_repository().list(COLLECTIONS["flags"])
    if open_only:
        flags = [f for f in flags if not f.get("resolved_at")]
    return flags


def resolve_flag(flag_id: str, by: str, note: str | None = None) -> dict | None:
    """Backwards-compatible flag resolution.

    Defaults to 'approved' disposition; the J5 inbox uses
    :func:`disposition_flag` directly when the user picks reject or
    defer instead.
    """
    return disposition_flag(flag_id, by=by, disposition="approved", note=note)


def disposition_flag(
    flag_id: str,
    *,
    by: str,
    disposition: str,
    note: str | None = None,
) -> dict | None:
    """Apply an App Flow J5 disposition (approve / reject / defer).

    - **approved**: the flag is resolved as accepted; the suggested
      change should be applied by whichever workflow owns it
      (catalogue edit, KG edge commit, etc.).
    - **rejected**: the flag is resolved as declined. App Flow J5
      mandates a reason — the caller is expected to enforce non-empty
      ``note`` before invoking this.
    - **deferred**: the flag stays open but is marked with a cooldown
      so the nightly proposer doesn't re-flood the inbox with it.
    """
    if disposition not in {"approved", "rejected", "deferred"}:
        raise ValueError(f"unknown disposition: {disposition!r}")

    repo = get_repository()
    flag = repo.get(COLLECTIONS["flags"], flag_id)
    if not flag:
        return None
    now = datetime.utcnow().isoformat()
    flag["disposition"] = disposition
    flag["disposition_by"] = by
    flag["disposition_note"] = note
    flag["disposition_at"] = now
    if disposition == "deferred":
        # Deferred flags stay open but get a recheck timestamp so the
        # nightly proposer can skip them until the cooldown elapses.
        flag["deferred_until"] = now
        flag.pop("resolved_at", None)
    else:
        flag["resolved_at"] = now
        flag["resolved_by"] = by
        flag["resolution_note"] = note
    repo.upsert(COLLECTIONS["flags"], flag_id, flag)
    return flag


def list_ingest_runs(limit: int = 20) -> list[dict]:
    runs = get_repository().list(COLLECTIONS["ingest_runs"])
    runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return runs[:limit]
