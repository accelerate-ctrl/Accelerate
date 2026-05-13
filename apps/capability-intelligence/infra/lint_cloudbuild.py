#!/usr/bin/env python3
"""Local Cloud Build linter.

Catches the exact error classes that bit us in production:
  * unescaped shell vars ($VAR not $$VAR) inside `entrypoint: bash` blocks —
    Cloud Build tries to resolve them as build substitutions and fails the
    build before bash ever runs.
  * empty resolution of built-in git substitutions (SHORT_SHA, COMMIT_SHA,
    BRANCH_NAME, TAG_NAME) — these are empty for manual `gcloud builds submit`
    and *produce malformed image tags / args*.
  * resulting bash scripts that don't even parse.
  * any user-defined `_FOO` substitution that's referenced but not declared.

Run:
  python infra/lint_cloudbuild.py infra/cloudbuild.yaml

Exits 0 if clean, non-zero (with a numbered list) on findings.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


# Built-ins always available, including for non-triggered builds.
ALWAYS_AVAILABLE = {
    "PROJECT_ID",
    "PROJECT_NUMBER",
    "BUILD_ID",
    "REVISION_ID",
    "LOCATION",
    "REPO_FULL_NAME",
}
# Built-ins only set for triggered builds from a Git source.
TRIGGER_ONLY = {
    "SHORT_SHA",
    "COMMIT_SHA",
    "BRANCH_NAME",
    "TAG_NAME",
    "REF_NAME",
    "TRIGGER_NAME",
    "TRIGGER_BUILD_CONFIG_PATH",
}
# Approximated; close enough for linting.

SUB_RE = re.compile(r"(?<!\$)\$\{([A-Z_][A-Z0-9_]*)\}")

# Safe, shell-quote-friendly placeholders for each substitution. The simulator
# renders these in place of real values so the resulting bash is syntactically
# valid (no angle brackets, no spaces).
PLACEHOLDERS = {
    "PROJECT_ID":     "digital-maturity-assessor",
    "PROJECT_NUMBER": "306195530103",
    "BUILD_ID":       "00000000-0000-0000-0000-000000000000",
    "REVISION_ID":    "rev-abc123",
    "LOCATION":       "us-central1",
    "REPO_FULL_NAME": "accelerate-ctrl/Accelerate",
    "SHORT_SHA":      "abc1234",
    "COMMIT_SHA":     "abc1234def5678",
    "BRANCH_NAME":    "main",
    "TAG_NAME":       "v0",
    "REF_NAME":       "main",
    # User-defined substitutions get a synthetic value via _udf_value().
}


def _udf_value(name: str) -> str:
    """A safe placeholder for a `_USER_DEFINED` substitution."""
    return name.lower().replace("_", "-").lstrip("-")


def find_substitutions(s: str) -> list[str]:
    """Return $ {NAME} references that are NOT preceded by an escape $."""
    return SUB_RE.findall(s)


def simulate(value: str, declared: set[str], trigger_mode: bool) -> tuple[str, list[str]]:
    """Return the Cloud-Build-resolved string + any warnings about empties."""
    warnings: list[str] = []
    def replace(m: re.Match) -> str:
        name = m.group(1)
        if name in declared:
            return _udf_value(name)
        if name in ALWAYS_AVAILABLE:
            return PLACEHOLDERS.get(name, name.lower())
        if name in TRIGGER_ONLY:
            if not trigger_mode:
                warnings.append(
                    f"built-in ${{{name}}} is EMPTY for manual `gcloud builds submit` — "
                    f"will inject empty string into the rendered value"
                )
                return ""
            return PLACEHOLDERS.get(name, name.lower())
        warnings.append(f"unknown substitution ${{{name}}} — typo or missing _UDF declaration")
        return "UNKNOWN-" + name
    return SUB_RE.sub(replace, value), warnings


def lint(path: Path) -> int:
    doc = yaml.safe_load(path.read_text())
    declared_subs = set((doc.get("substitutions") or {}).keys())

    findings: list[str] = []

    # 1) substitution-name correctness across the whole config
    flat = yaml.safe_dump(doc)
    for name in set(SUB_RE.findall(flat)):
        if name.startswith("_") and name not in declared_subs:
            findings.append(
                f"step references ${{{name}}} but it's not declared in `substitutions:`"
            )

    # 1b) Path-existence: any `cd <path>` or path-arg referenced inside a bash
    # block must resolve relative to either the repo root OR the
    # apps/capability-intelligence subdir (those are the two valid submit
    # roots). This catches the exit-127 class of failure where Cloud Build's
    # /workspace doesn't contain the path the script tries to cd into.
    repo_root = path.resolve()
    while repo_root.parent != repo_root and not (repo_root / "apps").is_dir():
        repo_root = repo_root.parent
    app_dir = repo_root / "apps" / "capability-intelligence"
    if app_dir.is_dir():
        # Detect bare `cd <literal-path>` (no $VAR) — those are the brittle ones.
        cd_re = re.compile(r"^\s*cd\s+([^\s$\"'`]+)", re.MULTILINE)
        for step in doc.get("steps") or []:
            sid = step.get("id") or "<step>"
            for arg in step.get("args") or []:
                if not isinstance(arg, str) or "\n" not in arg:
                    continue
                for m in cd_re.finditer(arg):
                    target = m.group(1)
                    if target.startswith("/workspace") or target.startswith("/"):
                        continue
                    found_at_root = (repo_root / target).is_dir()
                    found_at_app = (app_dir / target).is_dir()
                    if not (found_at_root and found_at_app):
                        findings.append(
                            f"[{sid}] bash block has `cd {target}` — exists at "
                            f"repo-root={found_at_root}, exists at app-dir={found_at_app}. "
                            f"Either path will be /workspace for one of the two submit "
                            f"modes (manual from app-dir vs from repo root), so the cd "
                            f"will fail and downstream commands like `pip install` or "
                            f"`ruff check` will exit 127. Use a runtime-resolved $$APP "
                            f"variable instead."
                        )

    # 2) Validate each `entrypoint: bash` step under both trigger modes.
    steps = doc.get("steps") or []
    for step in steps:
        sid = step.get("id") or step.get("name") or "<step>"
        if step.get("entrypoint") != "bash":
            # Non-bash steps: still check arg substitution, but no shell-var rules.
            for i, arg in enumerate(step.get("args") or []):
                if not isinstance(arg, str):
                    continue
                for mode in (False, True):
                    rendered, warns = simulate(arg, declared_subs, mode)
                    for w in warns:
                        findings.append(
                            f"[{sid}] arg[{i}] (trigger={mode}): {w}\n"
                            f"        rendered: {rendered!r}"
                        )
            continue

        # Bash steps: each script must be valid bash AFTER Cloud Build does
        # its $ {VAR} pass AND collapses $$ → $.
        for i, arg in enumerate(step.get("args") or []):
            if not isinstance(arg, str) or not arg.strip().startswith("#!") and "\n" not in arg:
                # Only the multi-line bash block matters
                if arg in ("-c",):
                    continue
            if "\n" not in arg:
                continue
            script = arg
            # 2a) Look for unescaped shell vars: $NAME or $(cmd) NOT preceded by $.
            for m in re.finditer(r"(?<!\$)\$(?:\(|[A-Za-z_]\w*)", script):
                tok = m.group(0)
                # Allow ${VAR} forms — those are Cloud Build subs handled separately.
                if tok.startswith("${"):
                    continue
                findings.append(
                    f"[{sid}] bash block: unescaped `{tok}` — Cloud Build will eat this "
                    f"before bash sees it. Use `$${tok[1:] if tok.startswith('$') else tok}`."
                )

            # 2b) Simulate substitution + $$→$ collapse, then run `bash -n` on the result.
            # If the script contains a fallback pattern that guards against
            # empty trigger-only built-ins, we suppress the "empty value"
            # warning because the script handles it intentionally.
            # Recognised fallback idiom (matches `resolve-tag` step):
            #     TAG="${SHORT_SHA}"
            #     if [ -z "$$TAG" ]; then TAG=... ; fi
            has_fallback_guard = bool(
                re.search(r'\bif\s+\[\s+-z\s+"\$\$\w+"\s+\]', script) or
                re.search(r'\bif\s+\[\s+-z\s+"\$\w+"\s+\]', script)
            )
            for mode_label, trigger_mode in (("manual", False), ("triggered", True)):
                rendered, warns = simulate(script, declared_subs, trigger_mode)
                rendered = rendered.replace("$$", "$")  # Cloud Build's final pass
                for w in warns:
                    if has_fallback_guard and "EMPTY for manual" in w:
                        continue  # script handles the empty case
                    findings.append(f"[{sid}] (mode={mode_label}): {w}")
                # bash -n
                with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as tmp:
                    tmp.write(rendered)
                    tmp_path = tmp.name
                try:
                    proc = subprocess.run(
                        ["bash", "-n", tmp_path],
                        capture_output=True, text=True, timeout=5,
                    )
                    if proc.returncode != 0:
                        findings.append(
                            f"[{sid}] (mode={mode_label}): bash syntax error in rendered "
                            f"script:\n{proc.stderr.strip()}\n--- rendered ---\n{rendered}\n---"
                        )
                finally:
                    Path(tmp_path).unlink(missing_ok=True)

            # 2c) Specifically: look for "...:<built-in-empty>" tag patterns.
            for nm in TRIGGER_ONLY:
                if f":${{{nm}}}" in script or f":${nm}" in script:
                    findings.append(
                        f"[{sid}] image tag uses `:${{{nm}}}` — empty for manual "
                        f"builds, will produce a malformed image reference. Use a "
                        f"runtime-computed tag instead."
                    )

        # 3) `args:` array forms (non-bash steps that bake substitution into args).
        if step.get("entrypoint") != "bash":
            for i, arg in enumerate(step.get("args") or []):
                if not isinstance(arg, str):
                    continue
                for mode_label, trigger_mode in (("manual", False),):
                    rendered, _ = simulate(arg, declared_subs, trigger_mode)
                    for nm in TRIGGER_ONLY:
                        if f":${{{nm}}}" in arg or arg.endswith(f":") or "<UNKNOWN" in rendered:
                            pass
                    # Detect the actual production bug: trailing ":" after substitution.
                    if rendered.endswith(":") and arg.endswith(":${" + "SHORT_SHA}"):
                        findings.append(
                            f"[{sid}] arg[{i}] (manual): rendered as {rendered!r} — "
                            f"empty SHORT_SHA leaves trailing `:` (malformed image ref)."
                        )

    if findings:
        print(f"✗ {len(findings)} lint finding(s) in {path}:\n")
        for n, f in enumerate(findings, 1):
            print(f"  {n}. {f}\n")
        return 1
    print(f"✓ {path} — clean for both manual + triggered builds")
    return 0


def main() -> int:
    if not shutil.which("bash"):
        print("bash not available", file=sys.stderr)
        return 2
    paths = [Path(p) for p in sys.argv[1:]] or [Path("infra/cloudbuild.yaml")]
    rc = 0
    for p in paths:
        rc |= lint(p)
    return rc


if __name__ == "__main__":
    sys.exit(main())
