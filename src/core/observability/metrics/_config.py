"""
Prometheus Metrics — Configuration and Prometheus client initialization.

Contains MetricsConfig, singleton management, and the Prometheus
client initialization logic.
"""

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ._collector import MetricsCollector

logger = logging.getLogger(__name__)

# ── Singleton ─────────────────────────────────────────────
_instance: Optional["MetricsCollector"] = None
_instance_lock = threading.Lock()


@dataclass
class MetricsConfig:
    """Configuration for Prometheus metrics collection.

    Attributes:
        enabled: Whether Prometheus metrics are active.
        port: Port for standalone metrics server (0 = shared with app).
        path: Metrics endpoint path.
        namespace: Metric namespace prefix.
        histograms: Whether to enable histogram metrics.
        default_buckets: Default histogram buckets in seconds.
    """
    enabled: bool = True
    port: int = 0
    path: str = "/metrics"
    namespace: str = "zenic"
    histograms: bool = True
    default_buckets: Tuple[float, ...] = (
        0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
    )

    @classmethod
    def from_env(cls) -> "MetricsConfig":
        """Create config from environment variables."""
        return cls(
            enabled=os.getenv("ZENIC_METRICS_ENABLED", "true").lower() == "true",
            port=int(os.getenv("ZENIC_METRICS_PORT", "0")),
            path=os.getenv("ZENIC_METRICS_PATH", "/metrics"),
        )


def _init_prometheus(config: MetricsConfig) -> dict:
    """Initialize Prometheus client metrics if available.

    Returns a dict with the initialized Prometheus objects,
    or empty dict if prometheus_client is not available.
    """
    prom_objects: Dict[str, Any] = {}

    try:
        import prometheus_client

        prom_objects["_prom_available"] = True
        ns = config.namespace

        # ── Counters ──────────────────────────────────
        prom_objects["_http_requests_total"] = prometheus_client.Counter(
            f"{ns}_http_requests_total",
            "Total HTTP requests",
            ["method", "path", "status"],
        )
        prom_objects["_rate_limit_accepted_total"] = prometheus_client.Counter(
            f"{ns}_rate_limit_accepted_total",
            "Total accepted requests",
        )
        prom_objects["_rate_limit_rejected_total"] = prometheus_client.Counter(
            f"{ns}_rate_limit_rejected_total",
            "Total rejected requests",
        )
        prom_objects["_auth_success_total"] = prometheus_client.Counter(
            f"{ns}_auth_success_total",
            "Total successful authentications",
            ["auth_method"],
        )
        prom_objects["_auth_failure_total"] = prometheus_client.Counter(
            f"{ns}_auth_failure_total",
            "Total failed authentications",
            ["auth_method"],
        )
        prom_objects["_tasks_completed_total"] = prometheus_client.Counter(
            f"{ns}_tasks_completed_total",
            "Total completed tasks",
            ["task_type", "worker_id"],
        )
        prom_objects["_tasks_failed_total"] = prometheus_client.Counter(
            f"{ns}_tasks_failed_total",
            "Total failed tasks",
            ["task_type", "worker_id"],
        )

        # ── Gauges ────────────────────────────────────
        prom_objects["_active_requests_gauge"] = prometheus_client.Gauge(
            f"{ns}_active_requests",
            "Currently active requests",
        )
        prom_objects["_ram_usage_mb_gauge"] = prometheus_client.Gauge(
            f"{ns}_ram_usage_mb",
            "Current RAM usage in MB",
        )
        prom_objects["_cpu_usage_pct_gauge"] = prometheus_client.Gauge(
            f"{ns}_cpu_usage_pct",
            "Current CPU usage percentage",
        )
        prom_objects["_uptime_seconds_gauge"] = prometheus_client.Gauge(
            f"{ns}_uptime_seconds",
            "Server uptime in seconds",
        )
        prom_objects["_circuit_breaker_state_gauge"] = prometheus_client.Gauge(
            f"{ns}_circuit_breaker_state",
            "Circuit breaker state (0=closed, 1=open, 2=half_open)",
            ["name"],
        )
        prom_objects["_task_queue_depth_gauge"] = prometheus_client.Gauge(
            f"{ns}_task_queue_depth",
            "Task queue depth",
            ["queue_name"],
        )
        prom_objects["_tenant_active_gauge"] = prometheus_client.Gauge(
            f"{ns}_tenants_active",
            "Number of active tenants",
        )

        # ── Histograms ────────────────────────────────
        if config.histograms:
            prom_objects["_http_request_duration_seconds"] = prometheus_client.Histogram(
                f"{ns}_http_request_duration_seconds",
                "HTTP request duration in seconds",
                ["method", "path"],
                buckets=config.default_buckets,
            )
            prom_objects["_task_duration_seconds"] = prometheus_client.Histogram(
                f"{ns}_task_duration_seconds",
                "Task execution duration in seconds",
                ["task_type"],
                buckets=config.default_buckets,
            )

        logger.info(
            "MetricsCollector: Prometheus client initialized (namespace=%s)",
            config.namespace,
        )

    except ImportError:
        prom_objects["_prom_available"] = False
        logger.info(
            "MetricsCollector: prometheus_client not installed — "
            "using internal counters with text format export"
        )

    return prom_objects
