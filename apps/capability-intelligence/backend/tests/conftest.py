import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_DATA = REPO_ROOT / "test-data"


@pytest.fixture(scope="session", autouse=True)
def _env() -> None:
    os.environ.setdefault("AUTH_MODE", "dev")
    os.environ.setdefault("AUTH_ALLOWED_DOMAIN", "zennify.com")
    os.environ.setdefault("ENV", "dev")


@pytest.fixture
def settings_for_tests(tmp_path, monkeypatch):
    """Per-test settings: fresh repo file, local catalogue dir = test-data/."""
    monkeypatch.setenv("LOCAL_REPOSITORY_PATH", str(tmp_path / "repo.json"))
    monkeypatch.setenv("LOCAL_CATALOGUE_DIR", str(TEST_DATA))
    monkeypatch.setenv("USE_GCP", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.services.repository import reset_repository_for_tests
    reset_repository_for_tests()
    yield get_settings()
    get_settings.cache_clear()
    reset_repository_for_tests()


@pytest.fixture
def client(settings_for_tests) -> TestClient:
    from app.main import create_app
    return TestClient(create_app())


@pytest.fixture
def auth_headers() -> dict:
    return {"Authorization": "Bearer dev-test@zennify.com"}


@pytest.fixture
def pillar1_file() -> Path:
    p = TEST_DATA / "Pillar 1" / "Pillar_1_Capability_Map_v14.0.xlsx"
    if not p.exists():
        pytest.skip(f"missing test data: {p}")
    return p
