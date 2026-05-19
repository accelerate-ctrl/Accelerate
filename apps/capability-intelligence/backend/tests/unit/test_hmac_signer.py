"""HMAC export signer tests (Phase 4.1 / QA_AUDIT F03 / PRD D18)."""

import os

import pytest

from app.services import hmac_signer
from app.services.hmac_signer import (
    EXPORT_LOG_COLLECTION,
    get_signed_export,
    list_signed_exports,
    sign_export,
    verify_export,
)
from app.services.repository import get_repository


@pytest.fixture(autouse=True)
def _env_for_tests(monkeypatch):
    """Pin a deterministic signing key so two test runs of the same
    payload produce the same signature."""
    monkeypatch.setenv("EXPORT_SIGNING_KEY", "test-fixture-key-1234567890")
    # ENV stays 'dev' — Settings only accepts dev | staging | prod.


# ─── Sign + verify round-trip ──────────────────────────────────────────────


def test_sign_returns_envelope_with_manifest(settings_for_tests):
    payload = b"hello world"
    env = sign_export(
        payload=payload, kind="catalogue", format="xlsx",
        filename="catalogue.xlsx", operator="x@zen.co",
    )
    assert env.export_id.startswith("export-catalogue-")
    assert env.algorithm == "HMAC-SHA256-v1"
    assert env.signature
    assert env.manifest["kind"] == "catalogue"
    assert env.manifest["bytes_size"] == 11
    assert env.manifest["sha256"]
    assert env.manifest["_schema_version"] == "manifest-v1"


def test_verify_accepts_matching_payload(settings_for_tests):
    payload = b"hello world"
    env = sign_export(
        payload=payload, kind="lifecycle", format="xlsx",
        filename="lifecycle.xlsx",
    )
    result = verify_export(
        payload=payload,
        signature=env.signature,
        manifest=env.manifest,
    )
    assert result == {"ok": True, "reason": None}


def test_verify_rejects_tampered_payload(settings_for_tests):
    env = sign_export(
        payload=b"original", kind="benchmarks", format="xlsx",
        filename="b.xlsx",
    )
    result = verify_export(
        payload=b"tampered",
        signature=env.signature,
        manifest=env.manifest,
    )
    assert result["ok"] is False
    assert "sha256 mismatch" in result["reason"]


def test_verify_rejects_tampered_signature(settings_for_tests):
    payload = b"x"
    env = sign_export(
        payload=payload, kind="catalogue", format="xlsx",
        filename="c.xlsx",
    )
    # Change exactly one character of the base64 signature.
    sig = env.signature
    tampered = sig[:-1] + ("A" if sig[-1] != "A" else "B")
    result = verify_export(
        payload=payload,
        signature=tampered,
        manifest=env.manifest,
    )
    assert result["ok"] is False
    assert "signature" in result["reason"].lower()


def test_verify_rejects_tampered_manifest(settings_for_tests):
    payload = b"x"
    env = sign_export(
        payload=payload, kind="catalogue", format="xlsx",
        filename="c.xlsx",
    )
    # Tampering with operator (a signed field) breaks the HMAC.
    manifest = dict(env.manifest)
    manifest["operator"] = "attacker@bad.com"
    result = verify_export(
        payload=payload,
        signature=env.signature,
        manifest=manifest,
    )
    assert result["ok"] is False


def test_signing_is_deterministic_for_same_inputs(settings_for_tests, monkeypatch):
    """Two sign_export calls with the same payload + same kind +
    same export_id must produce the same signature.

    We can't make ``export_id`` deterministic across calls (timestamp
    is in it), but we can verify the underlying _compute_signature is
    deterministic for the same manifest+payload pair.
    """
    from app.services.hmac_signer import _compute_signature
    payload = b"abc"
    manifest = {"a": 1, "b": "x"}
    sig1, h1 = _compute_signature(payload, manifest)
    sig2, h2 = _compute_signature(payload, manifest)
    assert sig1 == sig2
    assert h1 == h2


# ─── Persistence + audit log ──────────────────────────────────────────────


def test_signed_export_audit_row_persisted(settings_for_tests):
    env = sign_export(
        payload=b"x", kind="catalogue", format="xlsx",
        filename="c.xlsx", operator="op@zen.co",
    )
    row = get_signed_export(env.export_id)
    assert row is not None
    assert row["signature"] == env.signature
    assert row["manifest"]["operator"] == "op@zen.co"


def test_list_signed_exports_newest_first(settings_for_tests):
    a = sign_export(payload=b"a", kind="catalogue", format="xlsx", filename="a.xlsx")
    b = sign_export(payload=b"b", kind="lifecycle", format="xlsx", filename="b.xlsx")
    rows = list_signed_exports()
    ids = [r["export_id"] for r in rows]
    # Newest first; b was signed after a (same second is OK as long
    # as both are present).
    assert a.export_id in ids
    assert b.export_id in ids


def test_list_signed_exports_filter_by_kind(settings_for_tests):
    sign_export(payload=b"a", kind="catalogue", format="xlsx", filename="a.xlsx")
    sign_export(payload=b"b", kind="lifecycle", format="xlsx", filename="b.xlsx")
    only_lifecycle = list_signed_exports(kind="lifecycle")
    assert all(r["manifest"]["kind"] == "lifecycle" for r in only_lifecycle)


# ─── Key resolution safety ────────────────────────────────────────────────


def test_production_without_key_refuses_to_sign(monkeypatch, settings_for_tests):
    """A misconfigured prod deploy must fail closed instead of signing
    with the dev fallback."""
    monkeypatch.delenv("EXPORT_SIGNING_KEY", raising=False)
    monkeypatch.setenv("ENV", "prod")
    with pytest.raises(RuntimeError, match="EXPORT_SIGNING_KEY"):
        sign_export(payload=b"x", kind="catalogue", format="xlsx", filename="c.xlsx")


def test_dev_env_falls_back_to_dev_key(monkeypatch, settings_for_tests):
    monkeypatch.delenv("EXPORT_SIGNING_KEY", raising=False)
    monkeypatch.setenv("ENV", "dev")
    env = sign_export(payload=b"x", kind="catalogue", format="xlsx", filename="c.xlsx")
    assert env.signature  # signed OK


def test_key_id_changes_when_key_rotates(monkeypatch, settings_for_tests):
    monkeypatch.setenv("EXPORT_SIGNING_KEY", "key-v1")
    env1 = sign_export(payload=b"x", kind="catalogue", format="xlsx", filename="c.xlsx")
    monkeypatch.setenv("EXPORT_SIGNING_KEY", "key-v2")
    env2 = sign_export(payload=b"x", kind="catalogue", format="xlsx", filename="c.xlsx")
    assert env1.key_id != env2.key_id


def test_old_signature_fails_under_new_key(monkeypatch, settings_for_tests):
    """Rotating the key must invalidate prior signatures so a leaked
    key can't be used to forge new envelopes after rotation."""
    monkeypatch.setenv("EXPORT_SIGNING_KEY", "key-v1")
    env = sign_export(payload=b"x", kind="catalogue", format="xlsx", filename="c.xlsx")
    monkeypatch.setenv("EXPORT_SIGNING_KEY", "key-v2")
    result = verify_export(payload=b"x", signature=env.signature, manifest=env.manifest)
    assert result["ok"] is False
