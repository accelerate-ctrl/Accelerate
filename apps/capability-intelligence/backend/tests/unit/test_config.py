from app.config import Settings


def test_defaults():
    s = Settings()
    assert s.app_name == "capability-intelligence"
    assert s.env == "dev"
    assert s.auth_mode == "dev"
    assert s.auth_allowed_domain == "zennify.com"
    assert s.use_gcp is False
    assert "us-central1" in (s.gcp_region, s.vertex_region)


def test_env_override(monkeypatch):
    monkeypatch.setenv("AUTH_ALLOWED_DOMAIN", "example.com")
    monkeypatch.setenv("ENV", "staging")
    s = Settings()
    assert s.auth_allowed_domain == "example.com"
    assert s.env == "staging"
