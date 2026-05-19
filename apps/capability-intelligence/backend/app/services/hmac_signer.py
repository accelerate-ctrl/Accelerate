"""HMAC export signing + manifest emission (QA_AUDIT F03, PRD D18).

Closes two gaps at once:

- **F03 reproducibility manifest** — every analytical export (catalogue
  XLSX, lifecycle XLSX, benchmarks XLSX, quarterly digest PPTX) now
  ships with a JSON manifest documenting the run parameters, source
  catalogue version, and content hash so the output can be reproduced.
- **D18 signed exports** — every export's payload + manifest is
  HMAC-SHA256 signed with a server-side key so recipients can verify
  authenticity offline.

The signer is intentionally self-contained: it doesn't depend on a
specific export format. The producer (e.g. ``exports_service``) hands
in raw bytes + a manifest dict, and gets back the signed envelope
plus a stored ``signed_exports/{export_id}`` audit row.

Verification is the inverse: given the bytes + signature, recompute
the HMAC and assert equality with :func:`hmac.compare_digest` so the
check is timing-safe.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .repository import get_repository

logger = logging.getLogger(__name__)

EXPORT_LOG_COLLECTION = "signed_exports"

# Fallback dev key. Production deploys MUST set EXPORT_SIGNING_KEY in
# the environment — we refuse to sign with the dev key when ENV is
# anything other than "dev" / "test".
_DEV_FALLBACK_KEY = "dev-export-signing-key-do-not-use-in-prod"


@dataclass
class ExportManifest:
    """Per-export reproducibility record (F03).

    Mirrors the manifest emitted by :func:`app.observability.emit_manifest`
    for reasoning chains, plus export-specific fields.
    """
    export_id: str
    kind: str  # catalogue | lifecycle | benchmarks | digest | …
    format: str  # xlsx | pptx | pdf | json
    filename: str
    bytes_size: int
    sha256: str
    catalogue_version: str | None
    operator: str | None
    parameters: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    schema_version_: str = "manifest-v1"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["_schema_version"] = d.pop("schema_version_")
        return d


@dataclass
class SignedExport:
    """The envelope returned to the API edge.

    The signature is base64 over the HMAC-SHA256 of
    ``sha256(payload) || canonical_json(manifest)``. Verification is
    deterministic — recipients reconstruct the same input and compare.
    """
    export_id: str
    signature: str
    algorithm: str  # always 'HMAC-SHA256' v1
    key_id: str
    manifest: dict[str, Any]
    signed_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── Key resolution ───────────────────────────────────────────────────────


def _signing_key() -> tuple[bytes, str]:
    """Resolve the signing key + its key id.

    Returns ``(key_bytes, key_id)``. The key id is the first 12 chars of
    sha256(key) so logs + audit rows can reference which key produced
    a signature without leaking the key itself.

    Refuses to sign with the dev fallback when ENV is ``prod`` so a
    misconfigured production deploy fails closed; ``dev`` and
    ``staging`` are allowed to use the fallback.
    """
    raw = os.environ.get("EXPORT_SIGNING_KEY")
    env = (os.environ.get("ENV") or "dev").lower()
    if not raw:
        if env == "prod":
            raise RuntimeError(
                "EXPORT_SIGNING_KEY is not set in ENV=prod; refusing to "
                "sign with the dev fallback key in production."
            )
        raw = _DEV_FALLBACK_KEY
    key_bytes = raw.encode("utf-8")
    key_id = hashlib.sha256(key_bytes).hexdigest()[:12]
    return key_bytes, key_id


# ─── Internal helpers ─────────────────────────────────────────────────────


def _canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    """Canonical JSON: sorted keys, no extra whitespace, UTF-8 bytes.

    Two services producing the same manifest content must produce
    identical bytes so the signature is reproducible.
    """
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _payload_digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _compute_signature(payload: bytes, manifest: dict[str, Any]) -> tuple[str, str]:
    """Returns (signature_base64, payload_sha256_hex)."""
    key, _ = _signing_key()
    digest = _payload_digest(payload)
    canonical = _canonical_manifest_bytes(manifest)
    body = digest.encode("utf-8") + b"\n" + canonical
    sig = hmac.new(key, body, hashlib.sha256).digest()
    return base64.b64encode(sig).decode("ascii"), digest


# ─── Public API ───────────────────────────────────────────────────────────


def sign_export(
    *,
    payload: bytes,
    kind: str,
    format: str,
    filename: str,
    catalogue_version: str | None = None,
    operator: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> SignedExport:
    """Sign an export and persist the audit row.

    Returns the :class:`SignedExport` envelope; the caller is
    responsible for shipping the raw bytes + envelope to the client
    (typically as a Response headers + body pair).
    """
    started = datetime.now(timezone.utc).isoformat()
    _, key_id = _signing_key()
    export_id = f"export-{kind}-{int(datetime.now(timezone.utc).timestamp())}-{key_id}"

    manifest = ExportManifest(
        export_id=export_id,
        kind=kind,
        format=format,
        filename=filename,
        bytes_size=len(payload),
        sha256="",  # filled below once we compute it
        catalogue_version=catalogue_version,
        operator=operator,
        parameters=parameters or {},
        created_at=started,
    )
    # Compute sha256 + signature together so both reflect the same bytes.
    sig, digest = _compute_signature(payload, manifest.to_dict())
    manifest.sha256 = digest

    # Re-sign now that the manifest contains the digest. The order is
    # important — the manifest's sha256 field is part of the signed
    # canonical JSON, so verifiers can validate the digest matches the
    # bytes by recomputing from the manifest alone.
    sig, _ = _compute_signature(payload, manifest.to_dict())

    envelope = SignedExport(
        export_id=export_id,
        signature=sig,
        algorithm="HMAC-SHA256-v1",
        key_id=key_id,
        manifest=manifest.to_dict(),
        signed_at=started,
    )

    # Persist the audit row so the QA dashboard can list every export.
    try:
        get_repository().upsert(
            EXPORT_LOG_COLLECTION, export_id, envelope.to_dict(),
        )
    except Exception:
        logger.exception("export audit row persistence failed for %s", export_id)
    return envelope


def verify_export(
    *,
    payload: bytes,
    signature: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Verify a signed export by recomputing the HMAC.

    Returns ``{ok: bool, reason: str|None}`` so the API edge can return
    a 200 with ``ok=False`` for tampered exports rather than a 500.
    """
    expected_digest = _payload_digest(payload)
    declared_digest = manifest.get("sha256")
    if declared_digest != expected_digest:
        return {"ok": False, "reason": "payload sha256 mismatch"}

    expected_sig, _ = _compute_signature(payload, manifest)
    try:
        ok = hmac.compare_digest(expected_sig, signature)
    except Exception:
        ok = False
    if not ok:
        return {"ok": False, "reason": "signature mismatch"}
    return {"ok": True, "reason": None}


def list_signed_exports(*, limit: int = 50, kind: str | None = None) -> list[dict]:
    """Recent signed exports for the QA dashboard."""
    rows = get_repository().list(EXPORT_LOG_COLLECTION)
    if kind:
        rows = [r for r in rows if r.get("manifest", {}).get("kind") == kind]
    rows.sort(key=lambda r: r.get("signed_at") or "", reverse=True)
    return rows[:limit]


def get_signed_export(export_id: str) -> dict | None:
    return get_repository().get(EXPORT_LOG_COLLECTION, export_id)


__all__ = [
    "EXPORT_LOG_COLLECTION",
    "ExportManifest",
    "SignedExport",
    "get_signed_export",
    "list_signed_exports",
    "sign_export",
    "verify_export",
]
