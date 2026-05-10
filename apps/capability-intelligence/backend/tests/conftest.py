import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def _env() -> None:
    os.environ.setdefault("AUTH_MODE", "dev")
    os.environ.setdefault("AUTH_ALLOWED_DOMAIN", "zennify.com")
    os.environ.setdefault("ENV", "dev")


@pytest.fixture
def client() -> TestClient:
    from app.config import get_settings
    get_settings.cache_clear()
    from app.main import create_app
    return TestClient(create_app())


@pytest.fixture
def auth_headers() -> dict:
    return {"Authorization": "Bearer dev-test@zennify.com"}
