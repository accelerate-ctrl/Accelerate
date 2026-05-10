"""Job runner — single entrypoint for every Cloud Run Job.

Usage:
    python -m app.jobs.runner <job_name> [--arg key=value ...]

Wraps the named ``run()`` callable in:
    - structured start/end log lines (OpenTelemetry-friendly)
    - timing
    - Pub/Sub completion event (no-op in dev)
    - non-zero exit on raised exceptions (Cloud Run treats this as
      failure → Cloud Tasks DLQ retry per the per-job manifest)
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
import time
import traceback
from typing import Any

from ..observability import emit_span, structured_log

logger = logging.getLogger(__name__)

ALL_JOBS = (
    "news_poll",
    "public_filings_poll",
    "jira_incremental",
    "sow_incremental",
    "sow_full_reindex",
    "lifecycle_scoring_daily",
    "benchmark_extrapolation_run",
    "benchmark_recompute_quarterly",
    "digest_quarterly",
    "deep_audit_weekly",
    "eval_run_weekly",
    "citation_verify_daily",
    "drift_check_daily",
    "evidence_promotion_nightly",
)


def _resolve_job(name: str):
    if name not in ALL_JOBS:
        raise SystemExit(f"unknown job: {name}; valid: {', '.join(ALL_JOBS)}")
    module = importlib.import_module(f"app.jobs.{name}")
    fn = getattr(module, "run", None)
    if not callable(fn):
        raise SystemExit(f"job {name} has no callable run()")
    return fn


def execute(name: str, **kwargs: Any) -> dict[str, Any]:
    """Run a job by name.  Returns the structured result dict."""
    started = time.time()
    structured_log("job.started", job=name, kwargs=kwargs)
    fn = _resolve_job(name)
    with emit_span(f"job.{name}"):
        try:
            result = fn(**kwargs) or {}
        except Exception as exc:  # noqa: BLE001
            elapsed = time.time() - started
            structured_log(
                "job.failed",
                job=name,
                elapsed_s=round(elapsed, 3),
                error=str(exc),
                level="error",
            )
            from ..services.event_bus import publish_event
            publish_event("job.failed", {"job": name, "error": str(exc), "elapsed_s": elapsed})
            raise
    elapsed = time.time() - started
    payload = {
        "job": name,
        "elapsed_s": round(elapsed, 3),
        "result": result,
        "status": "ok",
    }
    structured_log("job.completed", **payload)
    from ..services.event_bus import publish_event
    publish_event("job.completed", payload)
    return payload


def _parse_kwargs(items: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw in items or []:
        if "=" not in raw:
            continue
        key, val = raw.split("=", 1)
        out[key.strip()] = _coerce(val.strip())
    return out


def _coerce(raw: str) -> Any:
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.jobs.runner")
    parser.add_argument("job", choices=ALL_JOBS)
    parser.add_argument(
        "--arg", action="append", default=[],
        help="Job kwargs in key=value form (repeatable).",
    )
    args = parser.parse_args(argv)
    try:
        execute(args.job, **_parse_kwargs(args.arg))
        return 0
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
