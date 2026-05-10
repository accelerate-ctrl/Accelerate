"""FastAPI dependency providers."""
from fastapi import Depends

from .auth import AuthUser, get_current_user
from .config import Settings, get_settings


def settings_dep() -> Settings:
    return get_settings()


def auth_dep(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    return user
