"""
ZENIC-AGENTS v16 - Distributed Tracing (Phase 5)

OpenTelemetry-compatible tracing with Jaeger/OTLP export.
Provides request-level and operation-level tracing with
correlation IDs that flow through the entire pipeline.
"""

from ._config import TracingConfig, init_tracing, get_tracer
from ._context import (
    trace_span,
    get_current_trace_id,
    get_current_span_id,
    inject_trace_context,
    extract_trace_context,
)

__all__ = [
    "TracingConfig",
    "init_tracing",
    "get_tracer",
    "trace_span",
    "get_current_trace_id",
    "get_current_span_id",
    "inject_trace_context",
    "extract_trace_context",
]
