"""LLM health probe — /api/ready should include adapter status without
ever returning 5xx, even with bad creds."""

from fastapi.testclient import TestClient

from app.main import app


def test_ready_includes_llm_adapter_block(monkeypatch):
    """Dev mode (default in tests) reports adapters as ok with mode=dev."""
    monkeypatch.setenv("LLM_LIVE_MODE", "false")
    from app import config as cfg
    cfg.get_settings.cache_clear()

    c = TestClient(app)
    r = c.get("/api/ready")
    assert r.status_code == 200
    body = r.json()
    assert "llm" in body, f"missing llm block: {body}"
    adapters = body["llm"]["adapters"]
    assert adapters.get("live_mode") is False
    assert adapters["anthropic"]["status"] == "ok"
    assert adapters["anthropic"]["mode"] == "dev"
    assert adapters["vertex"]["status"] == "ok"
    assert adapters["vertex"]["mode"] == "dev"


def test_ready_never_5xx_on_probe_failure(monkeypatch):
    """Even if the probe itself raises, /api/ready must return 2xx."""
    from app.services.llm import router as llm_router

    def boom() -> dict:
        raise RuntimeError("simulated probe failure")
    monkeypatch.setattr(llm_router, "probe", boom)

    c = TestClient(app)
    r = c.get("/api/ready")
    assert r.status_code == 200
    body = r.json()
    # The fallback path stores probe_error, not status=error in adapters.
    assert "probe_error" in body["llm"]["adapters"]


def test_reasoning_run_returns_422_not_500_on_loop_failure(monkeypatch):
    """The boundary handler in /reasoning-chains/run must downgrade any
    consultant_loop exception to a 422 with a diagnostic body."""
    from app.services import consultant_loop

    def boom(**_kwargs):
        raise RuntimeError("simulated synthesis failure")
    monkeypatch.setattr(consultant_loop, "run", boom)

    c = TestClient(app)
    r = c.post(
        "/api/reasoning-chains/run",
        headers={"Authorization": "Bearer dev-test@zennify.com"},
        json={"query": "anything", "sub_cap_id": None, "model": "gemini-flash"},
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["error_type"] == "RuntimeError"
    assert "simulated synthesis failure" in detail["detail"]


def test_chat_message_includes_error_block_when_loop_fails(monkeypatch):
    """Chat must surface error_type + stage in the reply payload (not just
    a generic 'Lookup failed' string) so the UI can render an actionable
    diagnostic."""
    from app.services import chat_service, consultant_loop

    def boom(**_kwargs):
        raise RuntimeError("synth blew up")
    monkeypatch.setattr(consultant_loop, "run", boom)

    reply = chat_service.post_message(message="Tell me about P1C1.1.1", persist=False)
    assert reply.error is not None
    assert reply.error["error_type"] == "RuntimeError"
    assert "synth blew up" in reply.error["detail"]
