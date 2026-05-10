"""SOW ingestion: discover -> extract -> redact -> chunk -> mention-extract -> persist.

Local mode (no GCP creds): scan `LOCAL_SOWS_DIR` for files under one of the
status subfolders (active, prospect, inactive, archived). Parse via
text_extraction; redact via dlp_service; tokenize subcap mentions via
rapidfuzz against the catalogue; persist to repository.

GCP mode (Batch 9 ops): swap discover/download with Drive API; swap
text_extraction.extract() with Document AI; swap dlp_service.redact() with
Cloud DLP. Same persistence shape; same mention-extraction logic until
Batch 4 wires Gemini Flash for richer classification.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from rapidfuzz import fuzz

from . import catalogue_service as cat
from .dlp_service import redact
from .entity_resolver import known_entities, resolve
from .repository import get_repository
from .text_extraction import SUPPORTED_EXTS, extract

log = logging.getLogger(__name__)

SOWS_COLL = "sows"
CHUNKS_COLL = "sow_chunks"
MENTIONS_COLL = "sow_mentions"
INGEST_RUNS_COLL = "sow_ingest_runs"
CLIENTS_COLL = "clients"

SOW_STATUSES = {"active", "prospect", "inactive", "archived"}


@dataclass
class SowFile:
    sow_id: str
    file_name: str
    file_uri: str
    status: str  # active|prospect|inactive|archived
    source: str  # "local" | "drive"
    modified_at: datetime


@dataclass
class SowIngestResult:
    run_id: str
    started_at: datetime
    completed_at: datetime
    by: str
    files_attempted: int
    sows_loaded: int
    chunks_total: int
    mentions_total: int
    redactions_total: int
    sow_ids: list[str] = field(default_factory=list)


# ─── Discovery ───────────────────────────────────────────────────────────────


def discover_sows() -> list[SowFile]:
    from ..config import get_settings
    s = get_settings()

    if s.use_gcp and s.drive_sows_folder_id:
        return _discover_drive(s.drive_sows_folder_id)

    # Local fallback
    base_env = getattr(s, "local_sows_dir", None) or _default_local_sows_dir()
    if not base_env:
        return []
    return _discover_local(Path(base_env))


def _default_local_sows_dir() -> str | None:
    """If no env override, look for a sibling test-data/SOWs/ folder."""
    candidate = Path(__file__).resolve().parents[3] / "test-data" / "SOWs"
    return str(candidate) if candidate.exists() else None


def _discover_local(root: Path) -> list[SowFile]:
    out: list[SowFile] = []
    if not root.exists():
        return out
    for status in SOW_STATUSES:
        sub = root / status
        if not sub.exists():
            continue
        for path in sub.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTS:
                continue
            sow_id = _sow_id_for(status, path.name)
            out.append(SowFile(
                sow_id=sow_id,
                file_name=path.name,
                file_uri=f"file://{path.resolve()}",
                status=status,
                source="local",
                modified_at=datetime.fromtimestamp(path.stat().st_mtime),
            ))
    return out


def _discover_drive(folder_id: str) -> list[SowFile]:  # pragma: no cover — wired in cloud
    from .drive_service import _drive_client, _drive_list_children, _parse_drive_dt
    drive = _drive_client()
    out: list[SowFile] = []
    children = _drive_list_children(drive, folder_id)
    status_folders: list[tuple[str, str]] = []
    for c in children:
        if c["mimeType"] == "application/vnd.google-apps.folder" and c["name"].lower() in SOW_STATUSES:
            status_folders.append((c["name"].lower(), c["id"]))
    if not status_folders:
        # All files at root → tag as 'active' by default
        for f in children:
            ext = "." + f.get("name", "").rsplit(".", 1)[-1].lower()
            if ext in SUPPORTED_EXTS:
                sow_id = _sow_id_for("active", f["name"])
                out.append(SowFile(sow_id, f["name"], f"drive:{f['id']}", "active", "drive", _parse_drive_dt(f.get("modifiedTime"))))
    else:
        for status, fid in status_folders:
            for f in _drive_list_children(drive, fid):
                ext = "." + f.get("name", "").rsplit(".", 1)[-1].lower()
                if ext in SUPPORTED_EXTS:
                    sow_id = _sow_id_for(status, f["name"])
                    out.append(SowFile(sow_id, f["name"], f"drive:{f['id']}", status, "drive", _parse_drive_dt(f.get("modifiedTime"))))
    return out


def _sow_id_for(status: str, file_name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", Path(file_name).stem)
    return f"sow-{status}-{base.lower()}"


# ─── Read content ────────────────────────────────────────────────────────────


def _read_bytes(sow: SowFile) -> bytes:
    if sow.source == "local":
        return Path(sow.file_uri.removeprefix("file://")).read_bytes()
    # Drive
    from .drive_service import _drive_client
    drive = _drive_client()
    file_id = sow.file_uri.removeprefix("drive:")
    request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
    from io import BytesIO
    from googleapiclient.http import MediaIoBaseDownload
    buf = BytesIO()
    downloader = MediaIoBaseDownload(buf, request, chunksize=4 * 1024 * 1024)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


# ─── Chunking ────────────────────────────────────────────────────────────────


def chunk_text(text: str, *, target_chars: int = 1200, overlap: int = 100) -> list[str]:
    """Paragraph-aware chunker. Targets ~1200-char windows with 100-char overlap."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if not buf:
            buf = p
            continue
        if len(buf) + 2 + len(p) <= target_chars:
            buf = buf + "\n\n" + p
        else:
            chunks.append(buf)
            tail = buf[-overlap:] if overlap and len(buf) > overlap else ""
            buf = (tail + "\n\n" + p).strip()
    if buf:
        chunks.append(buf)
    return chunks


# ─── Subcap mention extraction ───────────────────────────────────────────────


@dataclass
class Mention:
    sub_cap_id: str
    confidence: float
    method: str
    excerpt: str
    char_offset: int
    chunk_index: int


_SUB_CAP_ID_RX = re.compile(r"\bP[1-4]C\d+\.\d+(?:\.\d+)?\b")


def extract_mentions(chunks: list[str], subcaps: list[dict]) -> list[Mention]:
    """Extract subcap mentions from chunked text.

    Two-strategy: exact ID match (high-confidence) + name fuzzy match
    (medium-confidence). Batch 4 wraps this with Gemini Flash for
    extracted-claim labelling.
    """
    out: list[Mention] = []
    by_id = {s["sub_cap_id"]: s for s in subcaps}
    name_lookup = {(s["sub_cap_name"] or "").lower(): s["sub_cap_id"] for s in subcaps}

    for ci, chunk in enumerate(chunks):
        # exact ID hits
        for m in _SUB_CAP_ID_RX.finditer(chunk):
            sid = m.group(0)
            if sid in by_id:
                out.append(Mention(
                    sub_cap_id=sid,
                    confidence=99.0,
                    method="exact_id",
                    excerpt=_excerpt_around(chunk, m.start(), 80),
                    char_offset=m.start(),
                    chunk_index=ci,
                ))

        # name fuzzy hits (only on subcaps without an exact-id hit in this chunk
        # to avoid double-counting)
        already = {h.sub_cap_id for h in out if h.chunk_index == ci}
        chunk_lower = chunk.lower()
        for name_l, sid in name_lookup.items():
            if sid in already or len(name_l) < 6:
                continue
            # cheap substring screen first
            if name_l in chunk_lower:
                idx = chunk_lower.index(name_l)
                out.append(Mention(
                    sub_cap_id=sid,
                    confidence=85.0,
                    method="name_substring",
                    excerpt=_excerpt_around(chunk, idx, 80),
                    char_offset=idx,
                    chunk_index=ci,
                ))
                already.add(sid)
                continue
            # token-set ratio for moderate fuzz tolerance
            score = fuzz.token_set_ratio(name_l, chunk_lower[:2000])
            if score >= 92:
                out.append(Mention(
                    sub_cap_id=sid,
                    confidence=float(score),
                    method="name_fuzzy",
                    excerpt=chunk[:160],
                    char_offset=0,
                    chunk_index=ci,
                ))
                already.add(sid)
    return out


def _excerpt_around(text: str, idx: int, span: int) -> str:
    a = max(0, idx - span)
    b = min(len(text), idx + span)
    return text[a:b]


# ─── Client-name guess ───────────────────────────────────────────────────────


def guess_client(text: str, file_name: str) -> tuple[str, str, float]:
    """Return (canonical_name, raw_name, confidence)."""
    # 1. Look for "Client: X" pattern
    m = re.search(r"(?:^|\n)\s*Client\s*[:\-]\s*([^\n,]+)", text)
    raw = m.group(1).strip() if m else ""
    if not raw:
        # 2. Try filename prefix (before _ or -)
        base = Path(file_name).stem
        raw = base.replace("_", " ").split(" ", 1)[0]
    res = resolve(raw, kind="client")
    if res.confidence > 0:
        return res.canonical, raw, res.confidence
    # 3. Last resort: scan known entities for substring hits in the first 2000 chars
    head = text[:2000]
    for canonical in known_entities("client"):
        if canonical.lower() in head.lower():
            return canonical, canonical, 75.0
    return raw or "Unknown", raw, 0.0


# ─── Orchestration ───────────────────────────────────────────────────────────


def ingest_all(*, by: str = "system") -> SowIngestResult:
    started = datetime.utcnow()
    repo = get_repository()
    with repo.defer_persist():
        return _ingest_all_inner(started=started, by=by)


def _ingest_all_inner(*, started, by: str) -> SowIngestResult:
    repo = get_repository()
    files = discover_sows()
    subcaps = cat.list_subcaps()

    sow_ids: list[str] = []
    chunks_total = 0
    mentions_total = 0
    redactions_total = 0

    for f in files:
        try:
            content = _read_bytes(f)
            doc = extract(content, file_name=f.file_name)
        except Exception as e:
            log.exception("extraction failed for %s", f.sow_id)
            repo.upsert("flags", f"flag-ingestfail-{f.sow_id}-{int(started.timestamp())}", {
                "flag_id": f"flag-ingestfail-{f.sow_id}-{int(started.timestamp())}",
                "kind": "INGEST_FAILURE",
                "severity": "MEDIUM",
                "target_type": "sow",
                "target_id": f.sow_id,
                "title": f"SOW extraction failed: {f.file_name}",
                "detail": str(e),
                "detected_at": datetime.utcnow().isoformat(),
                "detected_by": "system",
            })
            continue

        red = redact(doc.text)
        chunks = chunk_text(red.text)
        client_canonical, client_raw, client_conf = guess_client(red.text, f.file_name)
        mentions = extract_mentions(chunks, subcaps)
        content_hash = hashlib.sha256(content).hexdigest()

        # Persist sow doc
        sow_doc = {
            "sow_id": f.sow_id,
            "file_name": f.file_name,
            "file_uri": f.file_uri,
            "status": f.status,
            "source": f.source,
            "modified_at": f.modified_at.isoformat(),
            "ingested_at": started.isoformat(),
            "client_name": client_canonical,
            "client_raw": client_raw,
            "client_confidence": client_conf,
            "page_count": doc.page_count,
            "char_count": doc.char_count,
            "chunk_count": len(chunks),
            "mention_count": len(mentions),
            "redaction_method": red.redaction_method,
            "redaction_summary": red.redaction_summary,
            "content_sha256": content_hash,
            "extractor": doc.extractor,
        }
        repo.upsert(SOWS_COLL, f.sow_id, sow_doc)

        # Persist chunks (replace this sow's slice)
        old_chunks = repo.list(CHUNKS_COLL, {"sow_id": f.sow_id})
        for oc in old_chunks:
            repo.delete(CHUNKS_COLL, oc["chunk_id"])
        chunk_docs = []
        for i, c in enumerate(chunks):
            chunk_id = f"{f.sow_id}-c{i:04d}"
            chunk_docs.append((chunk_id, {
                "chunk_id": chunk_id,
                "sow_id": f.sow_id,
                "chunk_index": i,
                "text": c,
                "char_count": len(c),
            }))
        if chunk_docs:
            repo.upsert_many(CHUNKS_COLL, chunk_docs)

        # Persist mentions (replace this sow's slice)
        old_mentions = repo.list(MENTIONS_COLL, {"sow_id": f.sow_id})
        for om in old_mentions:
            repo.delete(MENTIONS_COLL, om["mention_id"])
        mention_docs = []
        for i, m in enumerate(mentions):
            mention_id = f"{f.sow_id}-m{i:04d}"
            mention_docs.append((mention_id, {
                "mention_id": mention_id,
                "sow_id": f.sow_id,
                "sub_cap_id": m.sub_cap_id,
                "confidence": m.confidence,
                "method": m.method,
                "excerpt": m.excerpt,
                "char_offset": m.char_offset,
                "chunk_index": m.chunk_index,
                "client_name": client_canonical,
                "status": f.status,
                "ingested_at": started.isoformat(),
            }))
        if mention_docs:
            repo.upsert_many(MENTIONS_COLL, mention_docs)

        # Upsert client doc
        if client_canonical and client_canonical != "Unknown":
            existing = repo.get(CLIENTS_COLL, client_canonical) or {}
            client_doc = {
                "client_id": client_canonical,
                "name": client_canonical,
                "first_seen": existing.get("first_seen") or started.isoformat(),
                "last_seen": started.isoformat(),
                "sow_count": existing.get("sow_count", 0) + (1 if existing.get("client_id") != client_canonical or f.sow_id not in (existing.get("sow_ids") or []) else 0),
                "sow_ids": sorted(set((existing.get("sow_ids") or []) + [f.sow_id])),
                "statuses": sorted(set((existing.get("statuses") or []) + [f.status])),
            }
            repo.upsert(CLIENTS_COLL, client_canonical, client_doc)

        sow_ids.append(f.sow_id)
        chunks_total += len(chunks)
        mentions_total += len(mentions)
        redactions_total += sum(red.redaction_summary.values())

    completed = datetime.utcnow()
    run_id = f"sow-ingest-{int(started.timestamp())}"
    repo.upsert(INGEST_RUNS_COLL, run_id, {
        "run_id": run_id,
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "by": by,
        "files_attempted": len(files),
        "sows_loaded": len(sow_ids),
        "chunks_total": chunks_total,
        "mentions_total": mentions_total,
        "redactions_total": redactions_total,
        "sow_ids": sow_ids,
    })
    return SowIngestResult(
        run_id=run_id,
        started_at=started,
        completed_at=completed,
        by=by,
        files_attempted=len(files),
        sows_loaded=len(sow_ids),
        chunks_total=chunks_total,
        mentions_total=mentions_total,
        redactions_total=redactions_total,
        sow_ids=sow_ids,
    )


# ─── Read API ────────────────────────────────────────────────────────────────


def list_sows(*, status: str | None = None, client: str | None = None) -> list[dict]:
    flt: dict = {}
    if status:
        flt["status"] = status
    if client:
        flt["client_name"] = client
    return get_repository().list(SOWS_COLL, flt or None)


def get_sow(sow_id: str) -> dict | None:
    return get_repository().get(SOWS_COLL, sow_id)


def list_chunks_for(sow_id: str) -> list[dict]:
    chunks = get_repository().list(CHUNKS_COLL, {"sow_id": sow_id})
    chunks.sort(key=lambda c: c.get("chunk_index", 0))
    return chunks


def list_mentions_for_subcap(sub_cap_id: str) -> list[dict]:
    return get_repository().list(MENTIONS_COLL, {"sub_cap_id": sub_cap_id})


def list_mentions_for_sow(sow_id: str) -> list[dict]:
    return get_repository().list(MENTIONS_COLL, {"sow_id": sow_id})


def list_clients() -> list[dict]:
    return get_repository().list(CLIENTS_COLL)


def list_ingest_runs(limit: int = 20) -> list[dict]:
    runs = get_repository().list(INGEST_RUNS_COLL)
    runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return runs[:limit]


def trace_for_subcap(sub_cap_id: str) -> dict:
    """Project–Subcap Trace: every SOW + story touching this subcap."""
    sow_mentions = list_mentions_for_subcap(sub_cap_id)
    # Hydrate with SOW metadata
    sow_ids = sorted({m["sow_id"] for m in sow_mentions})
    sows_by_id = {s["sow_id"]: s for s in get_repository().list(SOWS_COLL) if s["sow_id"] in sow_ids}
    timeline = []
    for m in sow_mentions:
        sow = sows_by_id.get(m["sow_id"], {})
        timeline.append({
            "kind": "sow_mention",
            "sow_id": m["sow_id"],
            "file_name": sow.get("file_name"),
            "client_name": sow.get("client_name"),
            "status": sow.get("status"),
            "ingested_at": m.get("ingested_at"),
            "confidence": m.get("confidence"),
            "method": m.get("method"),
            "excerpt": m.get("excerpt"),
        })
    # Stories from canonical + jira (Batch 3 also)
    stories = (get_repository().list("stories_canonical", {"sub_cap_id": sub_cap_id}) +
               get_repository().list("jira_stories", {"sub_cap_id": sub_cap_id}))
    for s in stories:
        timeline.append({
            "kind": "story",
            "story_key": s.get("story_key"),
            "source_type": s.get("source_type") or "gen",
            "summary": s.get("summary"),
            "confidence": s.get("confidence_level"),
            "composite_score": s.get("composite_score"),
            "ingested_at": s.get("ingested_at"),
        })
    timeline.sort(key=lambda t: t.get("ingested_at") or "", reverse=True)
    return {
        "sub_cap_id": sub_cap_id,
        "sow_count": len(sows_by_id),
        "story_count": len(stories),
        "timeline": timeline,
    }
