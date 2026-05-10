"""Google Drive integration for catalogue ingestion.

Two modes:
  - GCP mode (use_gcp=True): real Google Drive API via service account.
    Requires GOOGLE_APPLICATION_CREDENTIALS pointing at SA JSON, and the
    Drive folder shared with the SA email.
  - Local mode (use_gcp=False or local_catalogue_dir set): scan a local
    directory for *.xlsx / *.xlsm files. Used by tests and dev without GCP.

Per-pillar version selection rules:
  1. Each pillar lives in its own subfolder. We accept these subfolder
     name patterns: "Pillar 1", "P1", "Pillar1", "1"; case-insensitive.
  2. Inside a pillar folder we list every Excel-like file
     (.xlsx, .xlsm, application/vnd.google-apps.spreadsheet).
  3. Skip any file whose name (case-insensitive) contains "inactive".
  4. Among the rest, pick the highest semver-ish "v<x>.<y>" token in the
     filename. If none has a version token, pick the most recently
     modified file.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

PILLAR_FOLDER_PATTERNS = [
    re.compile(r"^pillar[\s_-]*([1-4])\b", re.I),
    re.compile(r"^p\s*([1-4])\b", re.I),
    re.compile(r"^([1-4])[\s_.-]", re.I),
]

EXCEL_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel.sheet.macroEnabled.12": "xlsm",
    "application/vnd.ms-excel": "xls",
    "application/vnd.google-apps.spreadsheet": "gsheet",
}
EXCEL_EXTS = {".xlsx", ".xlsm", ".xls"}


@dataclass
class CatalogueFile:
    pillar_id: str  # P1..P4
    file_id: str    # Drive file id, or local absolute path
    file_name: str
    modified_at: datetime
    parsed_version: str | None  # e.g. "v14.0"
    is_google_sheet: bool = False
    source: str = "drive"  # "drive" | "local"


# ─── Public API ──────────────────────────────────────────────────────────────


def list_pillar_files() -> dict[str, CatalogueFile]:
    """Return one CatalogueFile per pillar, picking the active version."""
    from ..config import get_settings
    s = get_settings()

    if s.local_catalogue_dir:
        return _list_local(Path(s.local_catalogue_dir))
    if s.use_gcp and s.drive_pillars_folder_id:
        return _list_drive(s.drive_pillars_folder_id)
    return {}


def download_file(file: CatalogueFile) -> bytes:
    """Download file bytes (xlsx/xlsm). Google Sheets export to xlsx."""
    if file.source == "local":
        return Path(file.file_id).read_bytes()
    return _download_drive(file)


# ─── Pillar / version selection ──────────────────────────────────────────────


def _pillar_id_from_folder_name(name: str) -> str | None:
    for pat in PILLAR_FOLDER_PATTERNS:
        m = pat.search(name.strip())
        if m:
            return f"P{m.group(1)}"
    return None


VERSION_RX = re.compile(r"v(\d+)(?:[._](\d+))?", re.I)


def _parse_version_tuple(name: str) -> tuple[int, int] | None:
    matches = VERSION_RX.findall(name)
    if not matches:
        return None
    # take the LAST version-looking token in the name
    major, minor = matches[-1]
    return int(major), int(minor) if minor else 0


def _select_active_file(candidates: list[CatalogueFile]) -> CatalogueFile | None:
    """Per spec: skip 'inactive' names; pick highest version; fallback most-recent."""
    eligible = [c for c in candidates if "inactive" not in c.file_name.lower()]
    if not eligible:
        return None
    versioned = [(c, _parse_version_tuple(c.file_name)) for c in eligible]
    with_version = [(c, v) for c, v in versioned if v is not None]
    if with_version:
        with_version.sort(key=lambda x: x[1], reverse=True)
        return with_version[0][0]
    eligible.sort(key=lambda c: c.modified_at, reverse=True)
    return eligible[0]


def _stamp_parsed_version(c: CatalogueFile) -> CatalogueFile:
    v = _parse_version_tuple(c.file_name)
    if v:
        c.parsed_version = f"v{v[0]}.{v[1]}"
    return c


# ─── Local filesystem implementation ─────────────────────────────────────────


def _list_local(root: Path) -> dict[str, CatalogueFile]:
    if not root.exists():
        log.warning("local catalogue dir not found: %s", root)
        return {}

    by_pillar: dict[str, list[CatalogueFile]] = {}

    # Walk: each direct child folder may be a pillar; OR if root itself
    # contains files matching Pillar_<n>_*.xlsx, treat them as already-organized.
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in EXCEL_EXTS:
            continue
        # Try filename-derived pillar
        m = re.search(r"pillar[\s_-]*([1-4])", path.stem, re.I) or re.search(r"^P([1-4])", path.stem, re.I)
        if m:
            pillar_id = f"P{m.group(1)}"
        else:
            # Try parent folder name
            parent_pid = _pillar_id_from_folder_name(path.parent.name)
            if not parent_pid:
                continue
            pillar_id = parent_pid
        cf = CatalogueFile(
            pillar_id=pillar_id,
            file_id=str(path.resolve()),
            file_name=path.name,
            modified_at=datetime.fromtimestamp(path.stat().st_mtime),
            parsed_version=None,
            is_google_sheet=False,
            source="local",
        )
        by_pillar.setdefault(pillar_id, []).append(cf)

    out: dict[str, CatalogueFile] = {}
    for pid, candidates in by_pillar.items():
        chosen = _select_active_file(candidates)
        if chosen:
            out[pid] = _stamp_parsed_version(chosen)
    return out


# ─── Google Drive implementation ─────────────────────────────────────────────


def _drive_client():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    from ..config import get_settings
    s = get_settings()

    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    if s.google_application_credentials:
        creds = service_account.Credentials.from_service_account_file(
            s.google_application_credentials, scopes=scopes
        )
    else:
        # Fall back to ADC
        import google.auth
        creds, _ = google.auth.default(scopes=scopes)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _list_drive(root_folder_id: str) -> dict[str, CatalogueFile]:
    drive = _drive_client()
    by_pillar: dict[str, list[CatalogueFile]] = {}

    # 1. List immediate child folders of the root
    children = _drive_list_children(drive, root_folder_id)
    pillar_folders: list[tuple[str, str]] = []  # (pillar_id, folder_id)
    for c in children:
        if c["mimeType"] == "application/vnd.google-apps.folder":
            pid = _pillar_id_from_folder_name(c["name"])
            if pid:
                pillar_folders.append((pid, c["id"]))

    # If no pillar subfolders, scan files in the root folder directly.
    files_to_scan: list[tuple[str | None, dict]] = []
    if pillar_folders:
        for pid, fid in pillar_folders:
            for f in _drive_list_children(drive, fid):
                files_to_scan.append((pid, f))
    else:
        for f in children:
            files_to_scan.append((None, f))

    for pid, f in files_to_scan:
        mime = f.get("mimeType", "")
        if mime not in EXCEL_MIME_TYPES:
            continue
        # If pid wasn't pre-tagged, infer from filename
        actual_pid = pid or _infer_pid_from_name(f["name"])
        if not actual_pid:
            continue
        cf = CatalogueFile(
            pillar_id=actual_pid,
            file_id=f["id"],
            file_name=f["name"],
            modified_at=_parse_drive_dt(f.get("modifiedTime")),
            parsed_version=None,
            is_google_sheet=(mime == "application/vnd.google-apps.spreadsheet"),
            source="drive",
        )
        by_pillar.setdefault(actual_pid, []).append(cf)

    out: dict[str, CatalogueFile] = {}
    for pid, candidates in by_pillar.items():
        chosen = _select_active_file(candidates)
        if chosen:
            out[pid] = _stamp_parsed_version(chosen)
    return out


def _drive_list_children(drive, folder_id: str) -> list[dict]:
    items: list[dict] = []
    page_token = None
    while True:
        resp = drive.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, parents)",
            pageSize=200,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        items.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return items


def _infer_pid_from_name(name: str) -> str | None:
    m = re.search(r"pillar[\s_-]*([1-4])", name, re.I) or re.search(r"^P([1-4])\b", name, re.I)
    return f"P{m.group(1)}" if m else None


def _parse_drive_dt(s: str | None) -> datetime:
    if not s:
        return datetime.utcnow()
    try:
        # Drive returns RFC 3339, e.g. "2024-12-01T10:23:45.123Z"
        from dateutil import parser
        return parser.isoparse(s)
    except Exception:
        return datetime.utcnow()


def _download_drive(file: CatalogueFile) -> bytes:
    drive = _drive_client()
    if file.is_google_sheet:
        request = drive.files().export_media(
            fileId=file.file_id,
            mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        request = drive.files().get_media(fileId=file.file_id, supportsAllDrives=True)
    from io import BytesIO
    from googleapiclient.http import MediaIoBaseDownload
    buf = BytesIO()
    downloader = MediaIoBaseDownload(buf, request, chunksize=4 * 1024 * 1024)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()
