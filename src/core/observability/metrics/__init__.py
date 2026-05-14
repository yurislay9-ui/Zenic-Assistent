"""
ZENIC-AGENTS v16 - Prometheus Metrics (Phase 5)

Standard Prometheus client library integration for production metrics.
Replaces the custom text-format metrics with proper Prometheus
counters, gauges, histograms, and summaries.
"""

import time
from typing import Any, Optional

from ._config import MetricsConfig, _instance, _instance_lock
from ._collector import MetricsCollector

__all__ = [
    "MetricsCollector",
    "MetricsConfig",
    "get_metrics_collector",
    "metrics_middleware",
]


def get_metrics_collector(config: Optional[MetricsConfig] = None) -> MetricsCollector:
    """Get or create the singleton MetricsCollector.

    Args:
        config: Configuration (only used on first call).

    Returns:
        The global MetricsCollector instance.
    """
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = MetricsCollector(config)
        return _instance


async def metrics_middleware(request: Any, call_next: Any) -> Any:
    """FastAPI middleware that collects HTTP metrics.

    Records request duration, status codes, and active request count.

    Usage:
        app.middleware("http")(metrics_middleware)

    Args:
        request: FastAPI Request object.
        call_next: Next middleware/endpoint callable.

    Returns:
        Response from downstream.
    """
    collector = get_metrics_collector()
    collector.inc_active_requests()

    start_time = time.time()
    try:
        response = await call_next(request)
        duration = time.time() - start_time

        collector.record_request(
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration=duration,
        )
        return response
    except Exception:
        duration = time.time() - start_time
        collector.record_request(
            method=request.method,
            path=request.url.path,
            status=500,
            duration=duration,
        )
        raise
    finally:
        collector.dec_active_requests()
