"""
ZENIC-AGENTS v16 - Health Check Aggregator (Phase 5)

Comprehensive health checking for all subsystems.
Provides both liveness (/health) and readiness (/ready) probes
with detailed dependency status for Kubernetes-style deployments.

Health checks include:
- Orchestrator availability
- Auth database connectivity
- PostgreSQL coordination backend (if configured)
- Redis connectivity (if configured)
- Worker node status
- Task queue depth
- Resource governor (RAM/CPU)
- Circuit breaker states
- Disk space (for SQLite databases)

All checks have configurable timeouts and are async-friendly.
"""

import asyncio
import enum
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "HealthAggregator",
    "HealthStatus",
    "HealthCheckResult",
    "get_health_aggregator",
]


class HealthStatus(str, enum.Enum):
    """Health check result status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a single health check.

    Attributes:
        name: Check name (e.g. 'auth_db', 'redis', 'orchestrator').
        status: Health status.
        message: Human-readable status message.
        latency_ms: Check latency in milliseconds.
        details: Additional structured details.
    """
    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    message: str = ""
    latency_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


# Type for health check functions
HealthCheckFunc = Callable[[], Coroutine[Any, Any, HealthCheckResult]]


class HealthAggregator:
    """Aggregates health checks from all subsystems.

    Provides both liveness (is the process running?) and readiness
    (can it serve requests?) checks. Readiness checks include all
    dependencies; liveness checks are lightweight.

    Checks are registered as async callables and run concurrently
    with a configurable timeout.
    """

    def __init__(
        self,
        check_timeout: float = 5.0,
        liveness_checks: Optional[Dict[str, HealthCheckFunc]] = None,
        readiness_checks: Optional[Dict[str, HealthCheckFunc]] = None,
    ) -> None:
        self._check_timeout = check_timeout
        self._liveness_checks: Dict[str, HealthCheckFunc] = liveness_checks or {}
        self._readiness_checks: Dict[str, HealthCheckFunc] = readiness_checks or {}

    def register_liveness_check(self, name: str, check: HealthCheckFunc) -> None:
        """Register a liveness check.

        Liveness checks should be lightweight and fast — they
        determine if the process should be restarted.

        Args:
            name: Check name.
            check: Async callable that returns a HealthCheckResult.
        """
        self._liveness_checks[name] = check

    def register_readiness_check(self, name: str, check: HealthCheckFunc) -> None:
        """Register a readiness check.

        Readiness checks verify that all dependencies are available
        and the service can accept traffic.

        Args:
            name: Check name.
            check: Async callable that returns a HealthCheckResult.
        """
        self._readiness_checks[name] = check

    async def check_liveness(self) -> Dict[str, Any]:
        """Run liveness checks.

        Returns:
            Dict with 'status' and per-check results.
        """
        results = await self._run_checks(self._liveness_checks)
        overall = self._compute_overall_status(results)
        return {
            "status": overall.value,
            "checks": {r.name: {
                "status": r.status.value,
                "message": r.message,
                "latency_ms": round(r.latency_ms, 2),
            } for r in results},
            "timestamp": time.time(),
        }

    async def check_readiness(self) -> Dict[str, Any]:
        """Run readiness checks.

        Returns:
            Dict with 'ready', 'status', and per-check results.
        """
        results = await self._run_checks(self._readiness_checks)
        overall = self._compute_overall_status(results)
        return {
            "ready": overall != HealthStatus.UNHEALTHY,
            "status": overall.value,
            "checks": {r.name: {
                "status": r.status.value,
                "message": r.message,
                "latency_ms": round(r.latency_ms, 2),
                **r.details,
            } for r in results},
            "timestamp": time.time(),
        }

    async def _run_checks(
        self,
        checks: Dict[str, HealthCheckFunc],
    ) -> List[HealthCheckResult]:
        """Run health checks concurrently with timeout.

        Args:
            checks: Dict of check name -> async callable.

        Returns:
            List of HealthCheckResult objects.
        """
        if not checks:
            return []

        async def run_one(name: str, check: HealthCheckFunc) -> HealthCheckResult:
            start = time.time()
            try:
                result = await asyncio.wait_for(
                    check(),
                    timeout=self._check_timeout,
                )
                result.latency_ms = (time.time() - start) * 1000
                return result
            except asyncio.TimeoutError:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Timeout after {self._check_timeout}s",
                    latency_ms=(time.time() - start) * 1000,
                )
            except Exception as exc:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=str(exc),
                    latency_ms=(time.time() - start) * 1000,
                )

        tasks = [run_one(name, check) for name, check in checks.items()]
        return await asyncio.gather(*tasks)

    @staticmethod
    def _compute_overall_status(results: List[HealthCheckResult]) -> HealthStatus:
        """Compute overall status from individual check results.

        Rules:
        - If any check is UNHEALTHY → overall UNHEALTHY
        - If any check is DEGRADED → overall DEGRADED
        - If all checks HEALTHY → overall HEALTHY
        - If no checks → UNKNOWN
        """
        if not results:
            return HealthStatus.UNKNOWN

        has_degraded = False
        for r in results:
            if r.status == HealthStatus.UNHEALTHY:
                return HealthStatus.UNHEALTHY
            if r.status == HealthStatus.DEGRADED:
                has_degraded = True

        if has_degraded:
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY


# ── Built-in Health Check Functions ───────────────────────

async def check_orchestrator(orchestrator: Any) -> HealthCheckResult:
    """Check if the orchestrator is available."""
    if orchestrator is None:
        return HealthCheckResult(
            name="orchestrator",
            status=HealthStatus.UNHEALTHY,
            message="Orchestrator not initialized",
        )
    return HealthCheckResult(
        name="orchestrator",
        status=HealthStatus.HEALTHY,
        message="Available",
    )


async def check_auth_db(auth_service: Any) -> HealthCheckResult:
    """Check auth database connectivity."""
    if auth_service is None:
        return HealthCheckResult(
            name="auth_db",
            status=HealthStatus.HEALTHY,
            message="Auth not configured (optional)",
        )
    try:
        stats = auth_service.get_stats()
        return HealthCheckResult(
            name="auth_db",
            status=HealthStatus.HEALTHY,
            message="Connected",
            details={"users": stats.get("total_users", 0)},
        )
    except Exception as exc:
        return HealthCheckResult(
            name="auth_db",
            status=HealthStatus.UNHEALTHY,
            message=f"Connection failed: {exc}",
        )


async def check_coordination_backend(backend: Any) -> HealthCheckResult:
    """Check coordination backend (PostgreSQL/Memory) connectivity."""
    if backend is None:
        return HealthCheckResult(
            name="coordination_backend",
            status=HealthStatus.HEALTHY,
            message="Not configured (optional)",
        )
    try:
        result = await asyncio.wait_for(
            backend.health_check(),
            timeout=3.0,
        )
        healthy = result.get("healthy", False)
        return HealthCheckResult(
            name="coordination_backend",
            status=HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY,
            message=result.get("backend_type", "unknown"),
            details=result,
        )
    except Exception as exc:
        return HealthCheckResult(
            name="coordination_backend",
            status=HealthStatus.DEGRADED,
            message=f"Health check failed: {exc}",
        )


async def check_redis(redis_url: str = "redis://localhost:6379") -> HealthCheckResult:
    """Check Redis connectivity (if configured)."""
    try:
        import aioredis
        client = await aioredis.from_url(redis_url)
        await client.ping()
        await client.close()
        return HealthCheckResult(
            name="redis",
            status=HealthStatus.HEALTHY,
            message="Connected",
        )
    except ImportError:
        return HealthCheckResult(
            name="redis",
            status=HealthStatus.HEALTHY,
            message="Not installed (optional)",
        )
    except Exception as exc:
        return HealthCheckResult(
            name="redis",
            status=HealthStatus.DEGRADED,
            message=f"Connection failed: {exc}",
        )


async def check_resources(governor: Any) -> HealthCheckResult:
    """Check system resources via ResourceGovernor."""
    if governor is None:
        return HealthCheckResult(
            name="resources",
            status=HealthStatus.HEALTHY,
            message="Governor not configured",
        )
    try:
        status = governor.get_status()
        is_critical = governor.is_ram_critical()
        return HealthCheckResult(
            name="resources",
            status=HealthStatus.DEGRADED if is_critical else HealthStatus.HEALTHY,
            message="RAM critical" if is_critical else "Normal",
            details=status,
        )
    except Exception as exc:
        return HealthCheckResult(
            name="resources",
            status=HealthStatus.UNKNOWN,
            message=f"Check failed: {exc}",
        )


async def check_disk_space(path: str = ".", min_mb: float = 100.0) -> HealthCheckResult:
    """Check available disk space."""
    try:
        usage = os.statvfs(path)
        available_mb = (usage.f_bavail * usage.f_frsize) / (1024 * 1024)
        status = HealthStatus.HEALTHY if available_mb >= min_mb else HealthStatus.DEGRADED
        return HealthCheckResult(
            name="disk",
            status=status,
            message=f"{available_mb:.0f}MB available",
            details={"available_mb": round(available_mb, 1), "min_mb": min_mb},
        )
    except Exception as exc:
        return HealthCheckResult(
            name="disk",
            status=HealthStatus.UNKNOWN,
            message=f"Check failed: {exc}",
        )


# ── Singleton ─────────────────────────────────────────────
_health_aggregator: Optional[HealthAggregator] = None
_health_lock = threading.Lock()


def get_health_aggregator(
    check_timeout: float = 5.0,
) -> HealthAggregator:
    """Get or create the singleton HealthAggregator.

    Args:
        check_timeout: Timeout per health check in seconds.

    Returns:
        The global HealthAggregator instance.
    """
    global _health_aggregator
    with _health_lock:
        if _health_aggregator is None:
            _health_aggregator = HealthAggregator(check_timeout=check_timeout)
        return _health_aggregator
