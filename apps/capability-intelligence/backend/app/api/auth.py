"""Auth endpoints — surfaces OAuth config + a /me echo.

* ``GET /api/auth/config`` — public; returns the OAuth client_id +
  allowed-domain so the SPA can initialise Google Identity Services without
  baking secrets into the bundle.
* ``GET /api/auth/me`` — authenticated; returns the resolved AuthUser.
* ``POST /api/auth/google/callback`` — accepts ``{"id_token": "..."}`` from
  the OAuth flow (web or n8n) and verifies it. Returns the user payload on
  success. Used by the SPA after Google Identity returns a credential, and
  also serves as the n8n redirect target's verification endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth import AuthUser, _verify_google_oauth, get_current_user
from ..config import get_settings

router = APIRouter()


@router.get("/config")
def auth_config() -> dict:
    s = get_settings()
    return {
        "auth_mode": s.auth_mode,
        "google_oauth_client_id": s.google_oauth_client_id,
        "allowed_domain": s.auth_allowed_domain,
        "redirect_uris": s.google_oauth_redirect_uris,
    }


@router.get("/me")
def me(user: AuthUser = Depends(get_current_user)) -> dict:
    return {"uid": user.uid, "email": user.email, "name": user.name}


class CallbackBody(BaseModel):
    id_token: str


@router.post("/google/callback")
def google_callback(body: CallbackBody) -> dict:
    s = get_settings()
    if s.auth_mode == "dev":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "google_oauth verification disabled in dev mode")
    user = _verify_google_oauth(body.id_token)
    return {"uid": user.uid, "email": user.email, "name": user.name}
