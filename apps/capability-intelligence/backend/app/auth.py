"""Firebase ID-token verifier with a dev-mode bypass.

Dev: `Authorization: Bearer dev-<email>` accepted; email must end with the configured allowed domain.
Firebase: real verification — wired in Batch 1 once Firebase Admin SDK creds are configured.
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


def _verify_dev(token: str) -> AuthUser:
    if not token.startswith("dev-"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "dev-mode token must start with dev-")
    email = token.removeprefix("dev-").strip()
    if "@" not in email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "dev-mode token must encode an email")
    settings = get_settings()
    if not email.lower().endswith("@" + settings.auth_allowed_domain.lower()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"domain not allowed: {email}")
    return AuthUser(uid=email, email=email, name=None)


def _verify_firebase(token: str) -> AuthUser:  # pragma: no cover — wired in Batch 1
    # Will use firebase_admin.auth.verify_id_token here.
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "firebase auth wired in Batch 1")


def get_current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    token = _parse_bearer(authorization)
    settings = get_settings()
    if settings.auth_mode == "dev":
        return _verify_dev(token)
    return _verify_firebase(token)
