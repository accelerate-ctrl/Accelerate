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
    # Opt out of the catalogue_ontology corpus rebuild on every
    # refresh_pillar() — the production cron path keeps the corpus in
    # sync, but tests that don't exercise RAG don't need the ~30s
    # embedding overhead per refresh. RAG tests opt back in via the
    # ``with_corpus_rebuild`` fixture below.
    os.environ.setdefault("SKIP_CORPUS_REBUILD", "1")
    # Same opt-out for the sharded KG snapshot persister; refresh_pillar
    # otherwise spends ~5s persisting nodes/edges per test.
    os.environ.setdefault("SKIP_KG_SNAPSHOT", "1")


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


@pytest.fixture
def with_corpus_rebuild(monkeypatch):
    """Opt in to the catalogue_ontology corpus rebuild path.

    Phase 2.5 (FR-16) wires :func:`rebuild_corpus` into
    :func:`catalogue_service.refresh_pillar`; we opt out by default in
    the session-level _env() fixture so the test suite stays fast.
    Tests that exercise RAG retrieval should depend on this fixture to
    re-enable the rebuild path.
    """
    monkeypatch.delenv("SKIP_CORPUS_REBUILD", raising=False)
