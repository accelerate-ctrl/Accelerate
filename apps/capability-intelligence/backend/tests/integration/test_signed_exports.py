"""Signed-export endpoint tests (Phase 4.1)."""

import base64
import json

import pytest

from app.services import catalogue_service
from app.services.repository import get_repository

# Header names — keep in sync with app/api/exports.py.
SIG_HEADER = "X-Export-Signature"
KEY_HEADER = "X-Export-Key-Id"
ALG_HEADER = "X-Export-Algorithm"
MANIFEST_HEADER = "X-Export-Manifest"
EXPORT_ID_HEADER = "X-Export-Id"


@pytest.fixture(autouse=True)
def _signing_key(monkeypatch):
    monkeypatch.setenv("EXPORT_SIGNING_KEY", "integration-test-key")


@pytest.fixture
def seeded(client):
    # Refresh P1 so the catalogue export has rows to write.
    catalogue_service.refresh_pillar("P1", by="test")
    return client


def _read_manifest_header(response) -> dict:
    return json.loads(base64.b64decode(response.headers[MANIFEST_HEADER]))


def test_catalogue_export_carries_signature_headers(seeded, auth_headers):
    r = seeded.get("/api/exports/catalogue.xlsx", headers=auth_headers)
    assert r.status_code == 200
    assert SIG_HEADER in r.headers
    assert ALG_HEADER in r.headers
    assert r.headers[ALG_HEADER] == "HMAC-SHA256-v1"
    assert KEY_HEADER in r.headers
    assert MANIFEST_HEADER in r.headers
    # The manifest header decodes to a JSON object.
    manifest = _read_manifest_header(r)
    assert manifest["kind"] == "catalogue"
    assert manifest["format"] == "xlsx"
    assert manifest["filename"] == "catalogue.xlsx"
    assert manifest["sha256"]
    assert manifest["bytes_size"] == len(r.content)


def test_lifecycle_export_carries_signature_headers(seeded, auth_headers):
    r = seeded.get("/api/exports/lifecycle.xlsx", headers=auth_headers)
    assert r.status_code == 200
    assert r.headers.get(SIG_HEADER)


def test_clients_export_carries_signature_headers(seeded, auth_headers):
    r = seeded.get("/api/exports/clients.xlsx", headers=auth_headers)
    assert r.status_code == 200
    assert r.headers.get(SIG_HEADER)


def test_benchmarks_export_carries_signature_headers(seeded, auth_headers):
    r = seeded.get("/api/exports/benchmarks.xlsx", headers=auth_headers)
    assert r.status_code == 200
    assert r.headers.get(SIG_HEADER)


def test_verify_endpoint_accepts_valid_export(seeded, auth_headers):
    # Download a signed export.
    r = seeded.get("/api/exports/catalogue.xlsx", headers=auth_headers)
    payload_b64 = base64.b64encode(r.content).decode("ascii")
    manifest = _read_manifest_header(r)
    signature = r.headers[SIG_HEADER]

    verify = seeded.post(
        "/api/exports/verify",
        json={
            "payload_b64": payload_b64,
            "signature": signature,
            "manifest": manifest,
        },
        headers=auth_headers,
    )
    assert verify.status_code == 200
    assert verify.json() == {"ok": True, "reason": None}


def test_verify_endpoint_rejects_tampered_export(seeded, auth_headers):
    r = seeded.get("/api/exports/catalogue.xlsx", headers=auth_headers)
    manifest = _read_manifest_header(r)
    signature = r.headers[SIG_HEADER]
    # Flip one byte of the payload before re-encoding.
    tampered = bytearray(r.content)
    tampered[0] ^= 0xFF
    verify = seeded.post(
        "/api/exports/verify",
        json={
            "payload_b64": base64.b64encode(bytes(tampered)).decode("ascii"),
            "signature": signature,
            "manifest": manifest,
        },
        headers=auth_headers,
    )
    body = verify.json()
    assert body["ok"] is False


def test_verify_endpoint_invalid_base64_returns_422(seeded, auth_headers):
    r = seeded.post(
        "/api/exports/verify",
        json={
            "payload_b64": "!!!not-base64!!!",
            "signature": "sig",
            "manifest": {"sha256": "x"},
        },
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_signed_exports_audit_list(seeded, auth_headers):
    # Download two exports.
    seeded.get("/api/exports/catalogue.xlsx", headers=auth_headers)
    seeded.get("/api/exports/lifecycle.xlsx", headers=auth_headers)
    r = seeded.get("/api/exports/signed", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    kinds = {row["manifest"]["kind"] for row in body["exports"]}
    assert {"catalogue", "lifecycle"} <= kinds


def test_signed_exports_audit_by_id(seeded, auth_headers):
    r = seeded.get("/api/exports/catalogue.xlsx", headers=auth_headers)
    export_id = r.headers[EXPORT_ID_HEADER]
    detail = seeded.get(f"/api/exports/signed/{export_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["export_id"] == export_id


def test_signed_export_audit_row_carries_operator(seeded, auth_headers):
    seeded.get("/api/exports/catalogue.xlsx", headers=auth_headers)
    repo = get_repository()
    rows = repo.list("signed_exports")
    assert rows
    # auth_headers fixture uses dev-test@zennify.com
    assert any(
        (r.get("manifest", {}).get("operator") or "").startswith("test@")
        for r in rows
    )
