"""Story ingestion: canonical (gen_stories_export) + live Jira.

Canonical stories: parsed from `gen_stories_export.xlsx` (4,846 records in
Pillar 1). Carries the rich quality scores (composite_score, ac_quality,
sd_quality, delivery_score, confidence_score) that the simpler
`3_User_Stories_Catalogue` sheet doesn't have.

Live Jira: Atlassian REST when creds configured; otherwise no-op (we still
have the Pillar 1 sheet's JIRA-* refs in `stories` collection from Batch 1).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl

from .repository import get_repository

log = logging.getLogger(__name__)

CANONICAL_COLL = "stories_canonical"
JIRA_COLL = "jira_stories"
INGEST_RUNS_COLL = "stories_ingest_runs"

CANONICAL_HEADERS_REQUIRED = ["story_key", "sub_cap_id", "summary"]


@dataclass
class StoriesIngestResult:
    run_id: str
    started_at: datetime
    completed_at: datetime
    by: str
    canonical_loaded: int
    jira_loaded: int
    canonical_source: str | None = None
    jira_source: str | None = None
    schema_issues: list[str] = field(default_factory=list)


# ─── Canonical ingest from gen_stories_export.xlsx ───────────────────────────


def _discover_canonical_file() -> Path | None:
    """Look for `gen_stories_export.xlsx` next to the Pillar workbooks."""
    from ..config import get_settings
    s = get_settings()
    candidates: list[Path] = []
    if s.local_catalogue_dir:
        root = Path(s.local_catalogue_dir)
        candidates.extend(root.rglob("gen_stories_export*.xlsx"))
    # Also try the test-data root
    repo_root = Path(__file__).resolve().parents[3]
    candidates.extend((repo_root / "test-data").rglob("gen_stories_export*.xlsx"))
    # Pick most-recent
    files = [c for c in candidates if c.is_file()]
    if not files:
        return None
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def parse_canonical_stories(path: Path | None = None) -> list[dict]:
    p = path or _discover_canonical_file()
    if not p or not p.exists():
        return []
    wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
    ws = wb["gen_stories_export"] if "gen_stories_export" in wb.sheetnames else wb[wb.sheetnames[0]]

    headers: list[str] = []
    rows: list[dict] = []
    for r in ws.iter_rows(values_only=True):
        if not headers:
            if r and any(v is not None for v in r):
                headers = [str(v).strip() if v is not None else "" for v in r]
            continue
        if r is None or all(v is None or (isinstance(v, str) and not v.strip()) for v in r):
            continue
        d = {}
        for i, h in enumerate(headers):
            if not h:
                continue
            v = r[i] if i < len(r) else None
            if isinstance(v, str):
                v = v.strip() or None
            d[h] = v
        if not d.get("story_key"):
            continue
        rows.append(d)
    return rows


def ingest_canonical(*, by: str = "system") -> tuple[int, str | None, list[str]]:
    issues: list[str] = []
    repo = get_repository()
    path = _discover_canonical_file()
    if not path:
        return 0, None, ["no gen_stories_export.xlsx discovered"]
    rows = parse_canonical_stories(path)
    if not rows:
        return 0, str(path), ["empty workbook"]
    # Validate the required headers
    sample = rows[0]
    missing = [h for h in CANONICAL_HEADERS_REQUIRED if h not in sample]
    if missing:
        issues.append(f"missing headers: {missing}")
    # Replace
    upserts: list[tuple[str, dict[str, Any]]] = []
    now = datetime.utcnow().isoformat()
    for r in rows:
        sk = r["story_key"]
        doc = dict(r)
        doc["source_type"] = "gen_canonical"
        doc["ingested_at"] = now
        upserts.append((sk, doc))
    repo.replace_collection(CANONICAL_COLL, upserts)
    return len(upserts), str(path), issues


# ─── Jira ingest (Atlassian Cloud) ───────────────────────────────────────────


def ingest_jira(*, by: str = "system") -> tuple[int, str | None, list[str]]:
    """Fetch live Jira issues. Returns (count, source, issues).

    No-op when creds aren't configured. The pillar-1 workbook's
    `3_User_Stories_Catalogue` rows already populate the `stories` collection
    (Batch 1) which is sufficient for read-side surfaces in Batch 3 dev.
    """
    from ..config import get_settings
    s = get_settings()
    if not (s.jira_base_url and s.jira_email and s.jira_api_token and s.jira_project_keys):
        return 0, None, ["jira creds not configured (skipping live fetch)"]
    try:
        from atlassian import Jira  # type: ignore
        client = Jira(url=s.jira_base_url, username=s.jira_email, password=s.jira_api_token, cloud=True)
    except Exception as e:  # pragma: no cover — live cloud only
        return 0, s.jira_base_url, [f"Atlassian client init failed: {e}"]
    repo = get_repository()
    n = 0
    now = datetime.utcnow().isoformat()
    for project_key in s.jira_project_keys:
        try:
            issues = client.jql(f"project = {project_key}", limit=200) or {}
        except Exception as e:  # pragma: no cover — live cloud only
            log.warning("jira fetch failed for %s: %s", project_key, e)
            continue
        for issue in issues.get("issues", []):
            key = issue.get("key")
            if not key:
                continue
            fields = issue.get("fields", {})
            doc = {
                "story_key": key,
                "source_type": "jira",
                "summary": fields.get("summary"),
                "description": fields.get("description"),
                "status": (fields.get("status") or {}).get("name"),
                "issue_type": (fields.get("issuetype") or {}).get("name"),
                "project_key": project_key,
                "ingested_at": now,
            }
            repo.upsert(JIRA_COLL, key, doc)
            n += 1
    return n, s.jira_base_url, []


# ─── Orchestration ───────────────────────────────────────────────────────────


def refresh_all(*, by: str = "system") -> StoriesIngestResult:
    started = datetime.utcnow()
    repo = get_repository()
    # Wrap the whole ingest in a deferred-persist block so the JSON repo
    # writes once at the end instead of after every story (4,844 rows).
    with repo.defer_persist():
        canonical_n, canonical_src, can_issues = ingest_canonical(by=by)
        jira_n, jira_src, jira_issues = ingest_jira(by=by)
    completed = datetime.utcnow()
    run_id = f"stories-ingest-{int(started.timestamp())}"
    repo.upsert(INGEST_RUNS_COLL, run_id, {
        "run_id": run_id,
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "by": by,
        "canonical_loaded": canonical_n,
        "jira_loaded": jira_n,
        "canonical_source": canonical_src,
        "jira_source": jira_src,
        "schema_issues": can_issues + jira_issues,
    })
    return StoriesIngestResult(
        run_id=run_id,
        started_at=started,
        completed_at=completed,
        by=by,
        canonical_loaded=canonical_n,
        jira_loaded=jira_n,
        canonical_source=canonical_src,
        jira_source=jira_src,
        schema_issues=can_issues + jira_issues,
    )


# ─── Read API ────────────────────────────────────────────────────────────────


def list_canonical(filter: dict | None = None, limit: int = 200) -> list[dict]:
    rows = get_repository().list(CANONICAL_COLL, filter)
    return rows[:limit]


def list_jira(filter: dict | None = None, limit: int = 200) -> list[dict]:
    rows = get_repository().list(JIRA_COLL, filter)
    return rows[:limit]


def get_story(story_key: str) -> dict | None:
    """Look in canonical first, then jira, then the Batch-1 raw `stories` coll."""
    repo = get_repository()
    return (
        repo.get(CANONICAL_COLL, story_key)
        or repo.get(JIRA_COLL, story_key)
        or repo.get("stories", story_key)
    )


def list_stories_for_subcap(sub_cap_id: str) -> dict:
    """All story sources joined for a single subcap."""
    repo = get_repository()
    canonical = repo.list(CANONICAL_COLL, {"sub_cap_id": sub_cap_id})
    jira = repo.list(JIRA_COLL, {"sub_cap_id": sub_cap_id})
    raw = repo.list("stories", {"sub_cap_id": sub_cap_id})
    return {
        "sub_cap_id": sub_cap_id,
        "canonical": canonical,
        "jira": jira,
        "raw_pillar_sheet": raw,
    }


def list_runs(limit: int = 20) -> list[dict]:
    runs = get_repository().list(INGEST_RUNS_COLL)
    runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return runs[:limit]
