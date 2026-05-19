"""UI anti-pattern linter — rules + behaviour tests (UI/UX §11.3)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

INFRA = Path(__file__).resolve().parents[3] / "infra"


@pytest.fixture
def linter():
    spec = importlib.util.spec_from_file_location(
        "lint_ui_anti_patterns", INFRA / "lint_ui_anti_patterns.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lint_ui_anti_patterns"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_clean_file_has_no_findings(linter, tmp_path):
    p = tmp_path / "Card.tsx"
    _write(p, "export const Card = () => <div className='border rounded'/>;\n")
    assert linter._scan_file(p) == []


def test_box_shadow_flagged(linter, tmp_path):
    p = tmp_path / "Card.tsx"
    _write(p, "<div style={{ boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }} />\n")
    hits = linter._scan_file(p)
    # The css property name `boxShadow` should NOT match (we ban kebab
    # `box-shadow:` in styles). But the kebab variant in a string should.
    assert hits == []

    _write(p, "<style>{`.card { box-shadow: 0 4px 6px rgba(0,0,0,0.1); }`}</style>")
    hits = linter._scan_file(p)
    assert hits, "expected box-shadow string to be flagged"
    assert hits[0][1] == "box-shadow"


def test_linear_gradient_flagged(linter, tmp_path):
    p = tmp_path / "Hero.tsx"
    _write(p, "background: linear-gradient(90deg, red, blue);\n")
    hits = linter._scan_file(p)
    assert hits
    assert hits[0][1] == "linear-gradient"


def test_border_left_accent_flagged(linter, tmp_path):
    p = tmp_path / "Banner.tsx"
    _write(p, "className='border-l-4 border-l-zen-teal pl-3'\n")
    hits = linter._scan_file(p)
    assert hits
    assert hits[0][1] == "border-left-accent"


def test_comment_line_is_ignored(linter, tmp_path):
    p = tmp_path / "x.tsx"
    _write(p, "// box-shadow forbidden in this codebase\n")
    assert linter._scan_file(p) == []


def test_main_returns_zero_on_clean_dir(linter, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(linter, "ROOT", tmp_path)
    (tmp_path / "ok.tsx").write_text("export const X = () => null;\n")
    rc = linter.main()
    assert rc == 0


def test_main_returns_one_on_anti_pattern(linter, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(linter, "ROOT", tmp_path)
    (tmp_path / "bad.tsx").write_text(
        "<div style={{}}>box-shadow: 0 4px 6px rgba(0,0,0,0.1);</div>"
    )
    rc = linter.main()
    captured = capsys.readouterr()
    assert rc == 1
    assert "box-shadow" in captured.out


def test_live_frontend_tree_is_clean(linter):
    """Regression — the actual source tree must always be clean."""
    rc = linter.main()
    assert rc == 0
