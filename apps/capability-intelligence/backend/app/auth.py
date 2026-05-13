"""Authentication — three modes.

* ``dev``           — accept ``Bearer dev-<email>@<allowed_domain>``. Local only.
* ``firebase``      — verify a Firebase ID token via ``firebase_admin``.
* ``google_oauth``  — verify a Google ID token via Google's JWKS endpoint;
                       enforces ``aud == GOOGLE_OAUTH_CLIENT_ID`` and the
                       allowed domain. Prod default on Cloud Run; also the
                       endpoint that n8n's OAuth callback exchanges against.

Mode is selected by ``AUTH_MODE``. Firebase + Google use lazy imports so
dev runs need no extra dependencies.
"""
from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from .config import get_settings


@dataclass(frozen=True)
class AuthUser:
    uid: str
    email: str
    name: str | None = None


def _parse_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    return authorization.split(None, 1)[1].strip()


def _check_domain(email: str) -> None:
    settings = get_settings()
    allowed = (settings.auth_allowed_domain or "").lower().strip()
    if not allowed:
        return
    if not email.lower().endswith("@" + allowed):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"domain not allowed: {email}")


def _verify_dev(token: str) -> AuthUser:
    if not token.startswith("dev-"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "dev-mode token must start with dev-")
    email = token.removeprefix("dev-").strip()
    if "@" not in email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "dev-mode token must encode an email")
    _check_domain(email)
    return AuthUser(uid=email, email=email, name=None)


def _verify_firebase(token: str) -> AuthUser:  # pragma: no cover — exercised in cloud
    try:
        import firebase_admin
        from firebase_admin import auth as fb_auth
    except ImportError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "firebase-admin not installed") from exc
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    try:
        decoded = fb_auth.verify_id_token(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"firebase token invalid: {exc}") from exc
    email = decoded.get("email") or ""
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "firebase token missing email")
    _check_domain(email)
    return AuthUser(uid=decoded.get("uid") or email, email=email, name=decoded.get("name"))


_GA_REQUEST = None  # lazy module-level Request() — reuses HTTP connection pool


def _verify_google_oauth(token: str) -> AuthUser:  # pragma: no cover — exercised in cloud
    settings = get_settings()
    client_id = settings.google_oauth_client_id
    if not client_id:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "GOOGLE_OAUTH_CLIENT_ID not configured")
    # Fast-fail malformed tokens *before* the JWKS roundtrip — a well-formed
    # ID token always has three base64url segments separated by dots. This
    # turns brute-force token floods from p50≈1.7s (network) into p50<1ms.
    if token.count(".") != 2 or not all(token.split(".")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "google id_token invalid: malformed JWT structure")
    try:
        from google.auth.transport import requests as ga_requests
        from google.oauth2 import id_token as ga_id_token
    except ImportError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "google-auth not installed") from exc
    global _GA_REQUEST
    if _GA_REQUEST is None:
        _GA_REQUEST = ga_requests.Request()
    try:
        decoded = ga_id_token.verify_oauth2_token(token, _GA_REQUEST, client_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"google id_token invalid: {exc}") from exc
    if decoded.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "google id_token has bad issuer")
    email = decoded.get("email") or ""
    if not email or not decoded.get("email_verified"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "email not verified")
    _check_domain(email)
    return AuthUser(uid=decoded.get("sub") or email, email=email, name=decoded.get("name"))


_VERIFIERS = {
    "dev": _verify_dev,
    "firebase": _verify_firebase,
    "google_oauth": _verify_google_oauth,
}


def get_current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    token = _parse_bearer(authorization)
    settings = get_settings()
    verifier = _VERIFIERS.get(settings.auth_mode)
    if verifier is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"unknown AUTH_MODE: {settings.auth_mode}")
    return verifier(token)
