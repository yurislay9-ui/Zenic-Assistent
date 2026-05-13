"""
Distributed Tracing — Context Management and Decorators.

Contains get_current_trace_id, get_current_span_id, trace_span,
inject_trace_context, extract_trace_context, and the @traced decorator.
"""

import contextlib
import functools
import logging
import threading
import uuid
from typing import Any, Callable, Dict, Optional, TypeVar

from ._config import _tracing_enabled, _tracer

logger = logging.getLogger(__name__)

# Thread-local for correlation IDs when OTel is unavailable
_trace_context: threading.local = threading.local()


def get_current_trace_id() -> str:
    """Get the current trace ID from the active span or thread-local.

    Returns a 32-character hex string, or a new UUID if no trace is active.
    This is the key correlation ID that flows through all subsystems.
    """
    if _tracing_enabled:
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx and ctx.trace_id != 0:
                return format(ctx.trace_id, "032x")
        except Exception:
            pass

    trace_id = getattr(_trace_context, "trace_id", None)
    if trace_id:
        return trace_id

    new_id = uuid.uuid4().hex
    _trace_context.trace_id = new_id
    return new_id


def get_current_span_id() -> str:
    """Get the current span ID from the active span or thread-local.

    Returns a 16-character hex string, or a new UUID if no span is active.
    """
    if _tracing_enabled:
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx and ctx.span_id != 0:
                return format(ctx.span_id, "016x")
        except Exception:
            pass

    span_id = getattr(_trace_context, "span_id", None)
    if span_id:
        return span_id

    new_id = uuid.uuid4().hex[:16]
    _trace_context.span_id = new_id
    return new_id


@contextlib.contextmanager
def trace_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
    kind: Optional[Any] = None,
):
    """Context manager for creating a traced span.

    Works with or without OpenTelemetry. When OTel is not available,
    it manages correlation IDs in thread-local storage.

    Args:
        name: Span name (e.g. 'chat_completions', 'saga_step_execute').
        attributes: Optional dict of span attributes.
        kind: Span kind (SERVER, CLIENT, INTERNAL, etc.).

    Yields:
        The span object (OTel Span or a simple dict for fallback).
    """
    attrs = attributes or {}

    if _tracing_enabled and _tracer is not None:
        try:
            from opentelemetry import trace
            from opentelemetry.trace import SpanKind

            span_kind = kind
            if isinstance(kind, str):
                kind_map = {
                    "SERVER": SpanKind.SERVER,
                    "CLIENT": SpanKind.CLIENT,
                    "PRODUCER": SpanKind.PRODUCER,
                    "CONSUMER": SpanKind.CONSUMER,
                    "INTERNAL": SpanKind.INTERNAL,
                }
                span_kind = kind_map.get(kind.upper(), SpanKind.INTERNAL)

            with _tracer.start_as_current_span(name, kind=span_kind) as span:
                for k, v in attrs.items():
                    try:
                        span.set_attribute(k, v)
                    except Exception:
                        pass
                ctx = span.get_span_context()
                _trace_context.trace_id = format(ctx.trace_id, "032x")
                _trace_context.span_id = format(ctx.span_id, "016x")
                yield span
                return
        except Exception as exc:
            logger.debug("trace_span: OTel error, falling back: %s", exc)

    # Fallback: correlation-ID-only tracing
    parent_trace_id = getattr(_trace_context, "trace_id", None)
    parent_span_id = getattr(_trace_context, "span_id", None)

    _trace_context.trace_id = parent_trace_id or uuid.uuid4().hex
    _trace_context.span_id = uuid.uuid4().hex[:16]

    fallback_span = {
        "name": name,
        "trace_id": _trace_context.trace_id,
        "span_id": _trace_context.span_id,
        "parent_span_id": parent_span_id,
        "attributes": attrs,
    }

    try:
        yield fallback_span
    finally:
        _trace_context.trace_id = parent_trace_id or _trace_context.trace_id
        _trace_context.span_id = parent_span_id or _trace_context.span_id


def inject_trace_context(carrier: Dict[str, str]) -> Dict[str, str]:
    """Inject trace context into a carrier dict (for propagation)."""
    if _tracing_enabled:
        try:
            from opentelemetry import propagate
            propagate.inject(carrier)
            return carrier
        except Exception:
            pass

    carrier["x-trace-id"] = get_current_trace_id()
    carrier["x-span-id"] = get_current_span_id()
    return carrier


def extract_trace_context(carrier: Dict[str, str]) -> Optional[Any]:
    """Extract trace context from a carrier dict."""
    if _tracing_enabled:
        try:
            from opentelemetry import propagate
            return propagate.extract(carrier)
        except Exception:
            pass

    trace_id = carrier.get("x-trace-id")
    span_id = carrier.get("x-span-id")
    if trace_id:
        _trace_context.trace_id = trace_id
    if span_id:
        _trace_context.span_id = span_id
    return None


# ── Decorator for tracing functions ──────────────────────

F = TypeVar("F", bound=Callable)


def traced(name: Optional[str] = None, **span_attrs: Any) -> Callable[[F], F]:
    """Decorator that wraps a function in a trace span.

    Usage:
        @traced("process_pipeline", pipeline_level=5)
        def process_request(query: str) -> dict:
            ...

    Args:
        name: Span name (defaults to function.__qualname__).
        **span_attrs: Static span attributes.
    """
    def decorator(func: F) -> F:
        span_name = name or func.__qualname__

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_span(span_name, attributes=span_attrs):
                return func(*args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_span(span_name, attributes=span_attrs):
                return await func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator
