"""OpenTelemetry-friendly observability.

In production (when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set), the FastAPI
app is instrumented with OpenTelemetry's ASGI middleware so every request
becomes a span exported to Cloud Trace / OTLP. In dev (the default), we
fall back to structured logging only — no SDK import, no overhead.

The job runner uses :func:`emit_span` as a context manager so each Cloud
Run Job appears as one span in production traces, and as a structured
log line in dev.

Public surface:
    install_telemetry(app)          attach OTel middleware if configured
    emit_span(name)                 context manager with attributes
    structured_log(event, **kw)     logger.info-equivalent that writes
                                    a JSON-shaped record (compatible
                                    with Google Cloud Logging)
"""

from __future__ import annotations

import contextlib
import logging
import os
import time
from typing import Any, Iterator

import structlog

logger = structlog.get_logger(__name__)


# ─── Structured logging ─────────────────────────────────────────────────────


def structured_log(event: str, *, level: str = "info", **fields: Any) -> None:
    """Write a structured log line.

    The Batch-0 :func:`main.create_app` already configured structlog with
    JSON rendering, so the line is emitted as a single-line JSON dict to
    stdout — which Google Cloud Logging picks up automatically.
    """
    log_method = getattr(logger, level, logger.info)
    log_method(event, **fields)


# ─── Span emission ──────────────────────────────────────────────────────────


@contextlib.contextmanager
def emit_span(name: str, **attrs: Any) -> Iterator[None]:
    """Context manager that emits an OTel span when configured, else a
    structured ``span.start``/``span.end`` log pair."""
    tracer = _get_tracer()
    started = time.time()
    if tracer is not None:
        with tracer.start_as_current_span(name) as span:
            for k, v in attrs.items():
                try:
                    span.set_attribute(k, v)
                except Exception:  # noqa: BLE001
                    pass
            yield
        return
    structured_log("span.start", span=name, **attrs)
    try:
        yield
    finally:
        elapsed = time.time() - started
        structured_log("span.end", span=name, elapsed_s=round(elapsed, 4), **attrs)


def _get_tracer():
    """Return an OTel tracer when the SDK is importable + endpoint set."""
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return None
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        return trace.get_tracer("capability-intelligence")
    except Exception:  # noqa: BLE001
        return None


# ─── FastAPI install ────────────────────────────────────────────────────────


def install_telemetry(app) -> bool:
    """Wire OpenTelemetry into the FastAPI app when configured.

    Returns True if instrumentation was attached; False in dev / fallback.
    """
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        structured_log("otel.skipped", reason="no OTLP endpoint configured")
        return False
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        from opentelemetry.instrumentation.fastapi import (  # type: ignore[import-not-found]
            FastAPIInstrumentor,
        )
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-not-found]
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace.export import (  # type: ignore[import-not-found]
            BatchSpanProcessor,
        )
    except Exception as exc:  # noqa: BLE001
        structured_log(
            "otel.import_failed", reason=str(exc), level="warning",
        )
        return False

    resource = Resource.create({"service.name": "capability-intelligence"})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    structured_log("otel.installed", endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))
    return True
