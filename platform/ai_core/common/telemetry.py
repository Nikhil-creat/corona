"""OpenTelemetry tracing + Prometheus metrics bootstrap (no-ops cleanly if libs/endpoint absent)."""
from __future__ import annotations

import logging

from .config import Settings

log = logging.getLogger(__name__)


def setup_observability(service: str, settings: Settings, metrics_port: int | None = None) -> None:
    if metrics_port:
        try:
            from prometheus_client import start_http_server

            start_http_server(metrics_port)
        except Exception as exc:  # port already bound in embedded/test mode
            log.warning("metrics server not started: %s", exc)
    if not settings.otel_endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": service}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{settings.otel_endpoint}/v1/traces")))
        trace.set_tracer_provider(provider)
    except Exception as exc:
        log.warning("OpenTelemetry disabled: %s", exc)
