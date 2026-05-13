"""
Prometheus Metrics — MetricsCollector class.

Centralized Prometheus metrics collection with fallback
to internal counters when prometheus_client is unavailable.
"""

import logging
import threading
import time
from typing import Any, Dict, Optional

from ._config import MetricsConfig, _init_prometheus

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Centralized Prometheus metrics collection for ZENIC-AGENTS.

    All metrics are lazily created on first use. The collector works
    with or without prometheus_client installed — when unavailable,
    it tracks counts internally and exports custom text format.

    Thread-safe: all operations are protected by locks.
    """

    def __init__(self, config: Optional[MetricsConfig] = None) -> None:
        self._config = config or MetricsConfig()
        self._lock = threading.Lock()
        self._prom_available = False

        # Internal counters for fallback mode
        self._request_count: int = 0
        self._request_count_by_path: Dict[str, int] = {}
        self._request_count_by_status: Dict[int, int] = {}
        self._active_requests: int = 0
        self._rate_limit_accepted: int = 0
        self._rate_limit_rejected: int = 0
        self._auth_success: int = 0
        self._auth_failure: int = 0
        self._circuit_breaker_open: Dict[str, bool] = {}
        self._task_queue_depth: Dict[str, int] = {}
        self._start_time: float = time.time()

        # Initialize Prometheus
        prom_objects = _init_prometheus(self._config)
        self._prom_available = prom_objects.get("_prom_available", False)
        for key, value in prom_objects.items():
            if key != "_prom_available":
                setattr(self, key, value)

    # ── HTTP Request Tracking ──────────────────────────────

    def record_request(
        self,
        method: str,
        path: str,
        status: int,
        duration: float,
    ) -> None:
        """Record an HTTP request."""
        with self._lock:
            self._request_count += 1
            self._request_count_by_path[path] = self._request_count_by_path.get(path, 0) + 1
            self._request_count_by_status[status] = self._request_count_by_status.get(status, 0) + 1

        if self._prom_available:
            try:
                self._http_requests_total.labels(
                    method=method, path=path, status=str(status),
                ).inc()
                if self._config.histograms:
                    self._http_request_duration_seconds.labels(
                        method=method, path=path,
                    ).observe(duration)
            except Exception as exc:
                logger.debug("Metrics: Failed to record request: %s", exc)

    def inc_active_requests(self) -> None:
        """Increment the active requests counter."""
        with self._lock:
            self._active_requests += 1
        if self._prom_available:
            try:
                self._active_requests_gauge.inc()
            except Exception:
                pass

    def dec_active_requests(self) -> None:
        """Decrement the active requests counter."""
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)
        if self._prom_available:
            try:
                self._active_requests_gauge.dec()
            except Exception:
                pass

    # ── Rate Limit Tracking ────────────────────────────────

    def record_rate_limit_accepted(self) -> None:
        """Record an accepted request (rate limiter allowed)."""
        with self._lock:
            self._rate_limit_accepted += 1
        if self._prom_available:
            try:
                self._rate_limit_accepted_total.inc()
            except Exception:
                pass

    def record_rate_limit_rejected(self) -> None:
        """Record a rejected request (rate limiter denied)."""
        with self._lock:
            self._rate_limit_rejected += 1
        if self._prom_available:
            try:
                self._rate_limit_rejected_total.inc()
            except Exception:
                pass

    # ── Auth Tracking ──────────────────────────────────────

    def record_auth_success(self, method: str = "jwt") -> None:
        """Record a successful authentication."""
        with self._lock:
            self._auth_success += 1
        if self._prom_available:
            try:
                self._auth_success_total.labels(auth_method=method).inc()
            except Exception:
                pass

    def record_auth_failure(self, method: str = "jwt") -> None:
        """Record a failed authentication."""
        with self._lock:
            self._auth_failure += 1
        if self._prom_available:
            try:
                self._auth_failure_total.labels(auth_method=method).inc()
            except Exception:
                pass

    # ── Circuit Breaker Tracking ───────────────────────────

    def update_circuit_breaker(self, name: str, state: str) -> None:
        """Update circuit breaker state metric."""
        state_map = {"closed": 0, "open": 1, "half_open": 2}
        value = state_map.get(state, 0)
        with self._lock:
            self._circuit_breaker_open[name] = state != "closed"
        if self._prom_available:
            try:
                self._circuit_breaker_state_gauge.labels(name=name).set(value)
            except Exception:
                pass

    # ── Task Queue Tracking ────────────────────────────────

    def update_task_queue_depth(self, queue_name: str, depth: int) -> None:
        """Update task queue depth metric."""
        with self._lock:
            self._task_queue_depth[queue_name] = depth
        if self._prom_available:
            try:
                self._task_queue_depth_gauge.labels(queue_name=queue_name).set(depth)
            except Exception:
                pass

    def record_task_completed(self, task_type: str, worker_id: str, duration: float = 0.0) -> None:
        """Record a completed task."""
        if self._prom_available:
            try:
                self._tasks_completed_total.labels(
                    task_type=task_type, worker_id=worker_id,
                ).inc()
                if self._config.histograms and duration > 0:
                    self._task_duration_seconds.labels(task_type=task_type).observe(duration)
            except Exception:
                pass

    def record_task_failed(self, task_type: str, worker_id: str) -> None:
        """Record a failed task."""
        if self._prom_available:
            try:
                self._tasks_failed_total.labels(
                    task_type=task_type, worker_id=worker_id,
                ).inc()
            except Exception:
                pass

    # ── Resource Tracking ──────────────────────────────────

    def update_resources(self, ram_mb: float, cpu_pct: float) -> None:
        """Update resource usage metrics."""
        if self._prom_available:
            try:
                self._ram_usage_mb_gauge.set(ram_mb)
                self._cpu_usage_pct_gauge.set(cpu_pct)
            except Exception:
                pass

    def update_uptime(self, seconds: float) -> None:
        """Update uptime metric."""
        if self._prom_available:
            try:
                self._uptime_seconds_gauge.set(seconds)
            except Exception:
                pass

    def update_tenant_count(self, count: int) -> None:
        """Update active tenant count."""
        if self._prom_available:
            try:
                self._tenant_active_gauge.set(count)
            except Exception:
                pass

    # ── Export ─────────────────────────────────────────────

    def generate_text_metrics(self) -> str:
        """Generate Prometheus text-format metrics."""
        if self._prom_available:
            try:
                import prometheus_client
                return prometheus_client.generate_latest().decode("utf-8")
            except Exception:
                pass

        # Fallback: custom text format
        with self._lock:
            uptime = int(time.time() - self._start_time)
            lines = [
                f"# HELP {self._config.namespace}_uptime_seconds Server uptime in seconds",
                f"# TYPE {self._config.namespace}_uptime_seconds gauge",
                f"{self._config.namespace}_uptime_seconds {uptime}",
                f"# HELP {self._config.namespace}_requests_total Total HTTP requests",
                f"# TYPE {self._config.namespace}_requests_total counter",
                f"{self._config.namespace}_requests_total {self._request_count}",
                f"# HELP {self._config.namespace}_active_requests Currently active requests",
                f"# TYPE {self._config.namespace}_active_requests gauge",
                f"{self._config.namespace}_active_requests {self._active_requests}",
                f"# HELP {self._config.namespace}_rate_limit_accepted_total Total accepted requests",
                f"# TYPE {self._config.namespace}_rate_limit_accepted_total counter",
                f"{self._config.namespace}_rate_limit_accepted_total {self._rate_limit_accepted}",
                f"# HELP {self._config.namespace}_rate_limit_rejected_total Total rejected requests",
                f"# TYPE {self._config.namespace}_rate_limit_rejected_total counter",
                f"{self._config.namespace}_rate_limit_rejected_total {self._rate_limit_rejected}",
                f"# HELP {self._config.namespace}_auth_success_total Total successful authentications",
                f"# TYPE {self._config.namespace}_auth_success_total counter",
                f"{self._config.namespace}_auth_success_total {self._auth_success}",
                f"# HELP {self._config.namespace}_auth_failure_total Total failed authentications",
                f"# TYPE {self._config.namespace}_auth_failure_total counter",
                f"{self._config.namespace}_auth_failure_total {self._auth_failure}",
            ]

            for status, count in sorted(self._request_count_by_status.items()):
                lines.append(
                    f'{self._config.namespace}_requests_total{{status="{status}"}} {count}'
                )
            for name, is_open in self._circuit_breaker_open.items():
                value = 1 if is_open else 0
                lines.append(
                    f'{self._config.namespace}_circuit_breaker_state{{name="{name}"}} {value}'
                )
            for queue, depth in self._task_queue_depth.items():
                lines.append(
                    f'{self._config.namespace}_task_queue_depth{{queue_name="{queue}"}} {depth}'
                )

        return "\n".join(lines) + "\n"

    @property
    def is_prometheus_available(self) -> bool:
        """Whether prometheus_client is installed and initialized."""
        return self._prom_available
