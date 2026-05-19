"""Prompt YAML loader tests (Phase 5.1 / IMP-6)."""

import textwrap

import pytest

from app.services import prompt_loader


@pytest.fixture
def prompts_dir(tmp_path, monkeypatch):
    """Point PROMPTS_DIR at a writable tmp dir so each test seeds its
    own prompt fixtures without polluting the others."""
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
    prompt_loader.reload()
    yield tmp_path
    prompt_loader.reload()


def _write_prompt(dir_: "Path", op: str, version: str, content: str) -> None:
    op_dir = dir_ / op
    op_dir.mkdir(parents=True, exist_ok=True)
    (op_dir / f"{version}.yaml").write_text(textwrap.dedent(content), encoding="utf-8")


# ─── Load + render ─────────────────────────────────────────────────────────


def test_load_returns_prompt_spec(prompts_dir):
    _write_prompt(prompts_dir, "news_impact", "v1", """
        system: You are a strategist.
        user_template: |
            Item: {title}
            Body: {body}
        model: gemini-flash
    """)
    spec = prompt_loader.load("news_impact", version="v1")
    assert spec.operation == "news_impact"
    assert spec.version == "v1"
    assert spec.system == "You are a strategist."
    assert "{title}" in spec.user_template
    assert spec.model == "gemini-flash"


def test_render_substitutes_placeholders(prompts_dir):
    _write_prompt(prompts_dir, "news_impact", "v1", """
        system: You are a strategist.
        user_template: |
            Item: {title}
            Body: {body}
    """)
    system, user_text, spec = prompt_loader.render(
        "news_impact", title="OCC ruling", body="The OCC published...",
    )
    assert system == "You are a strategist."
    assert "OCC ruling" in user_text
    assert "The OCC published..." in user_text
    assert spec.version == "v1"


def test_render_missing_placeholder_raises_helpful_error(prompts_dir):
    _write_prompt(prompts_dir, "news_impact", "v1", """
        system: x
        user_template: |
            Title: {title}
            Body: {body}
    """)
    with pytest.raises(KeyError, match="body"):
        prompt_loader.render("news_impact", title="x")


def test_missing_user_template_raises(prompts_dir):
    _write_prompt(prompts_dir, "broken", "v1", """
        system: x
    """)
    with pytest.raises(ValueError, match="user_template"):
        prompt_loader.load("broken")


def test_missing_operation_raises(prompts_dir):
    with pytest.raises(FileNotFoundError, match="not found"):
        prompt_loader.load("does-not-exist")


def test_missing_version_raises(prompts_dir):
    _write_prompt(prompts_dir, "x", "v1", "system: a\nuser_template: b")
    with pytest.raises(FileNotFoundError):
        prompt_loader.load("x", version="v999")


# ─── Active version resolution ─────────────────────────────────────────────


def test_active_yaml_pointer_is_honored(prompts_dir):
    _write_prompt(prompts_dir, "op", "v1", "system: v1\nuser_template: x")
    _write_prompt(prompts_dir, "op", "v2", "system: v2\nuser_template: x")
    # Point active at v1 even though v2 is higher.
    (prompts_dir / "op" / "active.yaml").write_text("version: v1", encoding="utf-8")
    prompt_loader.reload()
    spec = prompt_loader.load("op")
    assert spec.version == "v1"
    assert spec.system == "v1"


def test_falls_back_to_highest_version_without_active(prompts_dir):
    _write_prompt(prompts_dir, "op", "v1", "system: v1\nuser_template: x")
    _write_prompt(prompts_dir, "op", "v2", "system: v2\nuser_template: x")
    _write_prompt(prompts_dir, "op", "v10", "system: v10\nuser_template: x")
    spec = prompt_loader.load("op")
    # v10 > v2 > v1 by numeric sort, not lexicographic.
    assert spec.version == "v10"
    assert spec.system == "v10"


def test_explicit_version_overrides_active(prompts_dir):
    _write_prompt(prompts_dir, "op", "v1", "system: v1\nuser_template: x")
    _write_prompt(prompts_dir, "op", "v2", "system: v2\nuser_template: x")
    (prompts_dir / "op" / "active.yaml").write_text("version: v2", encoding="utf-8")
    prompt_loader.reload()
    spec = prompt_loader.load("op", version="v1")
    assert spec.version == "v1"


def test_dotted_version_sort_keys(prompts_dir):
    _write_prompt(prompts_dir, "op", "v1.2", "system: 1.2\nuser_template: x")
    _write_prompt(prompts_dir, "op", "v1.10", "system: 1.10\nuser_template: x")
    spec = prompt_loader.load("op")
    # v1.10 > v1.2 numerically.
    assert spec.version == "v1.10"


# ─── Cache behaviour ──────────────────────────────────────────────────────


def test_cache_returns_same_object(prompts_dir):
    _write_prompt(prompts_dir, "op", "v1", "system: x\nuser_template: y")
    a = prompt_loader.load("op", version="v1")
    b = prompt_loader.load("op", version="v1")
    # Cache hit — identity preserved (same instance returned).
    assert a is b


def test_reload_picks_up_edits(prompts_dir):
    _write_prompt(prompts_dir, "op", "v1", "system: original\nuser_template: x")
    first = prompt_loader.load("op", version="v1")
    assert first.system == "original"
    _write_prompt(prompts_dir, "op", "v1", "system: edited\nuser_template: x")
    # Without reload, cache still serves the original.
    assert prompt_loader.load("op", version="v1").system == "original"
    prompt_loader.reload()
    assert prompt_loader.load("op", version="v1").system == "edited"


# ─── Discovery helpers ────────────────────────────────────────────────────


def test_list_operations_returns_dirs(prompts_dir):
    _write_prompt(prompts_dir, "alpha", "v1", "system: a\nuser_template: x")
    _write_prompt(prompts_dir, "beta", "v1", "system: b\nuser_template: x")
    ops = prompt_loader.list_operations()
    assert ops == ["alpha", "beta"]


def test_list_versions_sorted_highest_first(prompts_dir):
    _write_prompt(prompts_dir, "op", "v1", "system: a\nuser_template: x")
    _write_prompt(prompts_dir, "op", "v2", "system: b\nuser_template: x")
    _write_prompt(prompts_dir, "op", "v10", "system: c\nuser_template: x")
    assert prompt_loader.list_versions("op") == ["v10", "v2", "v1"]


def test_list_versions_ignores_active_yaml(prompts_dir):
    _write_prompt(prompts_dir, "op", "v1", "system: a\nuser_template: x")
    (prompts_dir / "op" / "active.yaml").write_text("version: v1", encoding="utf-8")
    assert prompt_loader.list_versions("op") == ["v1"]


def test_metadata_round_trip(prompts_dir):
    _write_prompt(prompts_dir, "op", "v1", """
        system: x
        user_template: y
        regression_dataset: golden_news_impact
        output_schema:
            type: object
            properties:
                impact_class:
                    type: string
        metadata:
            owner: pillar-leads
            cost_target_usd: 0.001
    """)
    spec = prompt_loader.load("op", version="v1")
    assert spec.regression_dataset == "golden_news_impact"
    assert spec.output_schema["type"] == "object"
    assert spec.metadata["owner"] == "pillar-leads"
