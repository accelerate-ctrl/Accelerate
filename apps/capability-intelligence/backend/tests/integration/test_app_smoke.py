"""Smoke test the app shell: every router stub responds with batch metadata."""
import pytest

# All 28 stubbed router prefixes (batch 0 ships these as stubs)
STUB_ROUTES = [
    "catalogue", "lens", "versions", "diffs", "flags", "suggestions", "trends", "news",
    "sows", "stories", "projects", "benchmarks", "lifecycle", "vendor-intel", "clients",
    "digest", "graph", "search", "audit", "validation-gates", "reasoning-chains", "sheets",
    "settings", "eval", "chat", "exports", "notifications", "personas", "what-if",
]


@pytest.mark.parametrize("prefix", STUB_ROUTES)
def test_stub_requires_auth(client, prefix):
    r = client.get(f"/api/{prefix}/_stub")
    assert r.status_code == 401, f"{prefix} should require auth"


@pytest.mark.parametrize("prefix", STUB_ROUTES)
def test_stub_with_auth(client, auth_headers, prefix):
    r = client.get(f"/api/{prefix}/_stub", headers=auth_headers)
    assert r.status_code == 200, f"{prefix} stub failed: {r.text}"
    body = r.json()
    assert body["status"] == "stub"
    assert "batch" in body and isinstance(body["batch"], int)


def test_openapi_lists_all_modules(client):
    r = client.get("/api/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    for prefix in STUB_ROUTES:
        assert any(p.startswith(f"/api/{prefix}/") for p in paths), f"{prefix} not in OpenAPI"
