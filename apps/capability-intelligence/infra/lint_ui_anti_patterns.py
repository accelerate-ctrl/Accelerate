#!/usr/bin/env python3
"""UI/UX anti-pattern linter (UI/UX Brief v1.0 §11.3, Phase 5).

The brief forbids decorative styling patterns that drift from the ZDS v2.4
design tokens. This script greps the frontend source for the three most
common drift patterns and exits non-zero on any hit so CI blocks merges:

1. ``box-shadow``         — ZDS uses no shadows (flat / outline-only).
2. ``linear-gradient``    — ZDS uses solid fills.
3. ``border-left.*accent`` — left-border accent stripes are banned.

Run:
    python infra/lint_ui_anti_patterns.py

Exits 0 if clean. Allow-list lives in :data:`ALLOWLIST_PATHS`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "src"

# Patterns are case-insensitive and match in template literals + CSS.
PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "box-shadow",
        re.compile(r"box-shadow", re.IGNORECASE),
        "ZDS v2.4 uses flat / outline-only styling — no drop shadows.",
    ),
    (
        "linear-gradient",
        re.compile(r"linear-gradient", re.IGNORECASE),
        "ZDS v2.4 uses solid fills — no gradients.",
    ),
    (
        "border-left-accent",
        re.compile(
            # Catches both CSS `border-left: 4px solid teal` and the
            # tailwind shorthand `border-l-4 border-l-zen-teal`.
            r"(border-left[^;\n]*(accent|brand|primary|teal|orange)"
            r"|border-l-\d[^\s'\"]*\s+border-l-[^\s'\"]*(accent|brand|primary|teal|orange|zen))",
            re.IGNORECASE,
        ),
        "ZDS bans left-border accent stripes — use a Card or Chip instead.",
    ),
]

# Allow-list: files where a hit is acceptable. Use sparingly — every entry
# is a deliberate decision, not a workaround. Add a comment justifying it.
ALLOWLIST_PATHS: set[Path] = set()


def _iter_source_files() -> list[Path]:
    if not ROOT.exists():
        return []
    exts = {".tsx", ".ts", ".jsx", ".js", ".css", ".scss"}
    return sorted(
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and p.suffix in exts
        and "node_modules" not in p.parts
    )


def _scan_file(path: Path) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return findings
    for lineno, line in enumerate(text.splitlines(), start=1):
        # Tailwind utility class `shadow-*` is the sanctioned way to opt
        # back into a shadow on rare elevated surfaces (e.g. dropdowns).
        # The literal `box-shadow:` CSS property is what we ban.
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        for name, pattern, _doc in PATTERNS:
            if pattern.search(line):
                findings.append((lineno, name, line.strip()))
    return findings


def main() -> int:
    files = _iter_source_files()
    if not files:
        print(f"no source files found under {ROOT}", file=sys.stderr)
        return 0

    total = 0
    for path in files:
        if path in ALLOWLIST_PATHS:
            continue
        for lineno, name, line in _scan_file(path):
            rel = path.relative_to(ROOT.parents[1])
            print(f"{rel}:{lineno} [{name}] {line}")
            total += 1

    if total:
        print(
            f"\nFound {total} UI anti-pattern hit(s). See UI/UX Brief §11.3.",
            file=sys.stderr,
        )
        return 1

    print(f"clean — {len(files)} files scanned, no anti-patterns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
