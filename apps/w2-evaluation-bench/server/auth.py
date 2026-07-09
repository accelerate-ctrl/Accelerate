"""Google Workspace sign-in for the BROWSER surfaces — Zennify org only.

Feature-flagged by W2_GOOGLE_CLIENT_ID (unset => the console falls back to the
bench-token modal, exactly the pre-Google behavior). Runners are unaffected
either way: the packet API keeps member-token auth (X-W2-Token) because
runners have no Google identity (client instruction 2026-07-07 overriding the
token-only console; recorded in docs/errata.md).

Flow: the console loads Google Identity Services with this client id ->
Google's own account chooser returns an ID-token credential -> POST
/auth/google verifies it server-side (signature via Google's certs, audience,
expiry through google-auth; then email_verified and the @zennify.com domain,
both the email suffix AND the `hd` Workspace claim when present) -> the
server mints an HMAC-signed session accepted by the /api middleware. The
domain gate is enforced HERE, not in the browser: a forged or non-Zennify
credential is rejected regardless of what the UI does.

W2_SESSION_SECRET should be set in production (Secret Manager) so sessions
survive instance restarts; without it a per-boot secret is generated (dev).
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import os
import secrets
import time

GOOGLE_CLIENT_ID = os.environ.get("W2_GOOGLE_CLIENT_ID", "")
ALLOWED_DOMAIN = os.environ.get("W2_ALLOWED_DOMAIN", "zennify.com")
SESSION_TTL_SECONDS = int(os.environ.get("W2_SESSION_TTL_HOURS", "12")) * 3600
_SECRET = os.environ.get("W2_SESSION_SECRET") or secrets.token_hex(32)

# The prototype's exact rejection copy (auth gate, docs/prototype).
DOMAIN_ERROR = ("Couldn’t sign in. Use your Zennify Workspace account "
                f"(ends in @{ALLOWED_DOMAIN}).")


def enabled() -> bool:
    return bool(GOOGLE_CLIENT_ID)


def domain_ok(email: str, hd: str | None = None) -> bool:
    """True only for verified members of the allowed Workspace domain.
    `hd` is Google's hosted-domain claim: absent on some account types, but
    when present it must match (a gmail.com user cannot spoof it)."""
    e = (email or "").strip().lower()
    if not e.endswith("@" + ALLOWED_DOMAIN) or e.count("@") != 1 or e.startswith("@"):
        return False
    if hd is not None and hd.lower() != ALLOWED_DOMAIN:
        return False
    return True


def mint_session(email: str, now: float | None = None) -> str:
    exp = int(now if now is not None else time.time()) + SESSION_TTL_SECONDS
    payload = f"{email}|{exp}"
    sig = hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()


def check_session(token: str, now: float | None = None) -> str | None:
    """Returns the signed-in email, or None for anything invalid/expired."""
    try:
        payload = base64.urlsafe_b64decode(token.encode()).decode()
        email, exp, sig = payload.rsplit("|", 2)
        good = hmac.new(_SECRET.encode(), f"{email}|{exp}".encode(),
                        hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            return None
        if int(exp) < (now if now is not None else time.time()):
            return None
        return email
    except Exception:
        return None


def verify_google_credential(credential: str) -> tuple[str, str | None]:
    """Verify a Google ID token; returns (email, hd). Raises ValueError on any
    problem. Deferred import: google-auth is only exercised when the feature
    is on (mocked in unit tests; network fetch of Google certs at runtime)."""
    from google.oauth2 import id_token
    from google.auth.transport import requests as garequests
    info = id_token.verify_oauth2_token(
        credential, garequests.Request(), GOOGLE_CLIENT_ID,
        clock_skew_in_seconds=10)
    if not info.get("email_verified"):
        raise ValueError("Google account email is not verified")
    return info.get("email", ""), info.get("hd")
