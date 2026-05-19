"""FastAPI dependency providers."""
import os

from fastapi import Depends, HTTPException, status

from .auth import AuthUser, get_current_user
from .config import Settings, get_settings


def settings_dep() -> Settings:
    return get_settings()


def auth_dep(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    return user


def admin_dep(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    """Admin-only gate (App Flow §7.4 AG-4 / J11).

    Admins are listed in the ``ADMIN_EMAILS`` env var, comma-separated.
    Pillar leads + regular users hit a 403 from this dependency.

    In dev mode, the bearer token is always ``dev-<email>``; setting
    ADMIN_EMAILS=test@zennify.com lets the dev session pass the gate.
    Production deploys configure this via Secret Manager + the
    service.yaml env block.
    """
    raw = os.environ.get("ADMIN_EMAILS", "")
    allowed = {a.strip().lower() for a in raw.split(",") if a.strip()}
    if not allowed:
        # Empty allow-list → no one is admin. Fail closed so a
        # misconfigured prod deploy doesn't accidentally expose
        # destructive endpoints to all users.
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "admin endpoint disabled (ADMIN_EMAILS not configured)",
        )
    if (user.email or "").lower() not in allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"admin privilege required (signed in as {user.email})",
        )
    return user
