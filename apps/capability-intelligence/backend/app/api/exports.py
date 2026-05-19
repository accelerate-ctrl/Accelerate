"""XLSX exports — catalogue / lifecycle / clients / benchmarks.

Phase 4.1 — every export is HMAC-signed (PRD D18) with a reproducibility
manifest (QA_AUDIT F03). The signature + manifest ride in response
headers so the bytes downloaded by the user can be verified offline.
"""

import base64
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ..deps import auth_dep
from ..services import exports_service, hmac_signer

router = APIRouter()

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Header names the FE / verifier tooling reads to lift the signature
# + manifest off a downloaded export. All headers are X-Export-* so
# they're easy to grep + don't collide with the standard set.
SIG_HEADER = "X-Export-Signature"
KEY_HEADER = "X-Export-Key-Id"
ALG_HEADER = "X-Export-Algorithm"
MANIFEST_HEADER = "X-Export-Manifest"
EXPORT_ID_HEADER = "X-Export-Id"


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "exports", "batch": 8, "status": "active"}


@router.get("/catalogue.xlsx")
def catalogue(user=Depends(auth_dep)) -> Response:
    return _signed_xlsx(
        exports_service.export_catalogue(),
        kind="catalogue", filename="catalogue.xlsx", operator=user.email,
    )


@router.get("/lifecycle.xlsx")
def lifecycle(user=Depends(auth_dep)) -> Response:
    return _signed_xlsx(
        exports_service.export_lifecycle(),
        kind="lifecycle", filename="lifecycle.xlsx", operator=user.email,
    )


@router.get("/clients.xlsx")
def clients(user=Depends(auth_dep)) -> Response:
    return _signed_xlsx(
        exports_service.export_clients(),
        kind="clients", filename="clients.xlsx", operator=user.email,
    )


@router.get("/benchmarks.xlsx")
def benchmarks(user=Depends(auth_dep)) -> Response:
    return _signed_xlsx(
        exports_service.export_benchmarks(),
        kind="benchmarks", filename="benchmarks.xlsx", operator=user.email,
    )


# ─── Phase 4.1 — verification + audit endpoints ────────────────────────────


class _VerifyRequest(BaseModel):
    """Verification payload — the client posts the base64-encoded
    bytes + the signature + the manifest that was attached to the
    download."""
    payload_b64: str
    signature: str
    manifest: dict


@router.post("/verify")
def verify(req: _VerifyRequest, _=Depends(auth_dep)) -> dict:
    """Verify a previously-signed export against the live server key.

    Returns ``{ok: bool, reason: str|None}``. Useful for compliance
    teams checking that a downloaded XLSX hasn't been tampered with.
    """
    try:
        payload = base64.b64decode(req.payload_b64)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"invalid base64 payload: {exc}") from exc
    return hmac_signer.verify_export(
        payload=payload, signature=req.signature, manifest=req.manifest,
    )


@router.get("/signed")
def list_signed(kind: str | None = None, limit: int = 50, _=Depends(auth_dep)) -> dict:
    """List recent signed exports for the QA / audit dashboard."""
    return {"exports": hmac_signer.list_signed_exports(limit=limit, kind=kind)}


@router.get("/signed/{export_id}")
def get_signed(export_id: str, _=Depends(auth_dep)) -> dict:
    row = hmac_signer.get_signed_export(export_id)
    if not row:
        raise HTTPException(404, f"signed export not found: {export_id}")
    return row


# ─── Helpers ──────────────────────────────────────────────────────────────


def _signed_xlsx(
    blob: bytes,
    *,
    kind: str,
    filename: str,
    operator: str | None,
) -> Response:
    """Sign the export and attach signature + manifest headers."""
    envelope = hmac_signer.sign_export(
        payload=blob,
        kind=kind,
        format="xlsx",
        filename=filename,
        operator=operator,
    )
    return Response(
        content=blob,
        media_type=XLSX_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            EXPORT_ID_HEADER: envelope.export_id,
            SIG_HEADER: envelope.signature,
            KEY_HEADER: envelope.key_id,
            ALG_HEADER: envelope.algorithm,
            # Manifest as base64-encoded JSON so header value stays
            # ASCII-safe regardless of the manifest content.
            MANIFEST_HEADER: base64.b64encode(
                json.dumps(envelope.manifest, sort_keys=True).encode("utf-8"),
            ).decode("ascii"),
        },
    )
