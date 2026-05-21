"""
ZENIC-AGENTS v16 - Health Check Aggregator (Phase 5 + Phase 3.4)

Comprehensive health checking for all subsystems.
Provides both liveness (/health) and readiness (/ready) probes
with detailed dependency status for Kubernetes-style deployments.

Health checks include:
- Orchestrator availability
- Auth database connectivity
- PostgreSQL coordination backend (if configured)
- Redis connectivity (if configured) — uses redis.asyncio (redis[hiredis])
- Worker node status
- Task queue depth
- Resource governor (RAM/CPU)
- Circuit breaker states
- Disk space (for SQLite databases)

Phase 3.4 updates:
- Replaced deprecated aioredis with redis.asyncio (redis[hiredis] package)
- Added check_postgresql() built-in health check
- Added check_circuit_breakers() for unified circuit breaker state
- Added register_default_checks() for auto-registration based on env
- Updated get_health_aggregator() to call register_default_checks()

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
    "check_redis",
    "check_postgresql",
    "check_circuit_breakers",
    "check_vector_store",
    "register_default_checks",
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
    """Check Redis connectivity using the modern redis.asyncio client.

    Phase 3.4: Replaced deprecated ``aioredis`` with ``redis.asyncio``
    from the ``redis[hiredis]`` package. The ``aioredis`` standalone package
    is deprecated — ``redis.asyncio`` is the recommended replacement.

    Args:
        redis_url: Redis connection URL.

    Returns:
        HealthCheckResult with connectivity status.
    """
    try:
        import redis.asyncio as aioredis  # type: ignore[import-untyped]

        client = aioredis.from_url(
            redis_url,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        try:
            await client.ping()
            return HealthCheckResult(
                name="redis",
                status=HealthStatus.HEALTHY,
                message="Connected",
            )
        finally:
            await client.close()
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


async def check_postgresql(
    database_url: Optional[str] = None,
) -> HealthCheckResult:
    """Check PostgreSQL connectivity.

    Phase 3.4: Built-in health check for PostgreSQL backend.
    Uses asyncpg for a lightweight connectivity test.

    Args:
        database_url: PostgreSQL connection URL. If not provided,
            reads from DATABASE_URL environment variable.

    Returns:
        HealthCheckResult with connectivity status.
    """
    db_url = database_url or os.environ.get("DATABASE_URL")
    if not db_url:
        return HealthCheckResult(
            name="postgresql",
            status=HealthStatus.HEALTHY,
            message="Not configured (optional)",
        )

    # Check if it's actually a PostgreSQL URL
    if not db_url.startswith("postgresql://") and not db_url.startswith("postgres://"):
        return HealthCheckResult(
            name="postgresql",
            status=HealthStatus.HEALTHY,
            message="Not a PostgreSQL URL (optional)",
        )

    try:
        import asyncpg  # type: ignore[import-untyped]

        conn = await asyncio.wait_for(
            asyncpg.connect(db_url),
            timeout=5.0,
        )
        try:
            result = await conn.fetchval("SELECT 1")
            version = await conn.fetchval("SELECT version()")
            return HealthCheckResult(
                name="postgresql",
                status=HealthStatus.HEALTHY,
                message="Connected",
                details={
                    "server_version": version.split(",")[0] if version else "unknown",
                },
            )
        finally:
            await conn.close()
    except ImportError:
        return HealthCheckResult(
            name="postgresql",
            status=HealthStatus.DEGRADED,
            message="asyncpg not installed — cannot verify PostgreSQL",
        )
    except asyncio.TimeoutError:
        return HealthCheckResult(
            name="postgresql",
            status=HealthStatus.UNHEALTHY,
            message="Connection timed out (5s)",
        )
    except Exception as exc:
        return HealthCheckResult(
            name="postgresql",
            status=HealthStatus.UNHEALTHY,
            message=f"Connection failed: {exc}",
        )


async def check_circuit_breakers(
    breaker_registry: Optional[Dict[str, Any]] = None,
) -> HealthCheckResult:
    """Check unified circuit breaker state.

    Phase 3.4: Aggregates the state of all registered circuit breakers
    and reports overall health.

    Args:
        breaker_registry: Dict mapping breaker names to CircuitBreaker
            instances. If not provided, tries to discover from
            the module-level registry.

    Returns:
        HealthCheckResult with aggregated circuit breaker state.
    """
    if breaker_registry is None:
        # Try to discover from the module-level registry
        try:
            from ..patterns.resilience.circuit_breaker import CircuitBreaker
            # No global registry — check if there's one in observability
            breaker_registry = getattr(
                check_circuit_breakers, "_registry", {}
            )
        except ImportError:
            breaker_registry = {}

    if not breaker_registry:
        return HealthCheckResult(
            name="circuit_breakers",
            status=HealthStatus.HEALTHY,
            message="No circuit breakers registered",
        )

    open_count = 0
    half_open_count = 0
    closed_count = 0
    breaker_details: Dict[str, Any] = {}

    for name, breaker in breaker_registry.items():
        try:
            stats = breaker.stats if hasattr(breaker, "stats") else {}
            state = stats.get("current_state", "closed")
            breaker_details[name] = {
                "state": state,
                "total_calls": stats.get("total_calls", 0),
                "total_failures": stats.get("total_failures", 0),
            }
            if state == "open":
                open_count += 1
            elif state == "half_open":
                half_open_count += 1
            else:
                closed_count += 1
        except Exception as exc:
            breaker_details[name] = {"state": "unknown", "error": str(exc)}

    total = len(breaker_registry)
    if open_count > 0:
        status = HealthStatus.DEGRADED if open_count < total else HealthStatus.UNHEALTHY
        message = f"{open_count}/{total} circuit(s) OPEN"
    elif half_open_count > 0:
        status = HealthStatus.DEGRADED
        message = f"{half_open_count}/{total} circuit(s) HALF_OPEN"
    else:
        status = HealthStatus.HEALTHY
        message = f"All {total} circuit(s) CLOSED"

    return HealthCheckResult(
        name="circuit_breakers",
        status=status,
        message=message,
        details={
            "total": total,
            "open": open_count,
            "half_open": half_open_count,
            "closed": closed_count,
            "breakers": breaker_details,
        },
    )


async def check_vector_store(
    vector_store: Any = None,
) -> HealthCheckResult:
    """Check vector store health.

    Phase 4.1: Built-in health check for the pgvector-backed
    vector store. Reports backend type, embedding count, and
    connectivity status.

    Args:
        vector_store: VectorStore instance. If not provided,
            tries to import from the vector module.

    Returns:
        HealthCheckResult with vector store status.
    """
    if vector_store is None:
        try:
            from ..vector.vector_store import get_vector_store
            vector_store = get_vector_store()
        except ImportError:
            return HealthCheckResult(
                name="vector_store",
                status=HealthStatus.HEALTHY,
                message="Vector store not available (optional)",
            )

    try:
        result = await asyncio.wait_for(
            vector_store.health_check(),
            timeout=5.0,
        )
        healthy = result.get("healthy", False)
        return HealthCheckResult(
            name="vector_store",
            status=HealthStatus.HEALTHY if healthy else HealthStatus.DEGRADED,
            message=f"Backend: {result.get('backend', 'unknown')}",
            details=result,
        )
    except asyncio.TimeoutError:
        return HealthCheckResult(
            name="vector_store",
            status=HealthStatus.DEGRADED,
            message="Health check timed out (5s)",
        )
    except Exception as exc:
        return HealthCheckResult(
            name="vector_store",
            status=HealthStatus.DEGRADED,
            message=f"Health check failed: {exc}",
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


# ── Auto-Registration ─────────────────────────────────────

def register_default_checks(
    aggregator: HealthAggregator,
    redis_url: Optional[str] = None,
    database_url: Optional[str] = None,
    breaker_registry: Optional[Dict[str, Any]] = None,
) -> None:
    """Auto-register all available health checks based on environment.

    Phase 3.4: Convenience function that inspects environment
    variables and registers the appropriate checks.

    Checks registered:
      - Liveness: disk space
      - Readiness: redis, postgresql, circuit_breakers (if configured)

    Args:
        aggregator: The HealthAggregator to register checks on.
        redis_url: Redis URL (falls back to REDIS_URL env var).
        database_url: PostgreSQL URL (falls back to DATABASE_URL env var).
        breaker_registry: Circuit breaker instances dict.
    """
    # ── Liveness checks (lightweight) ──
    aggregator.register_liveness_check("disk", lambda: check_disk_space())

    # ── Readiness checks (dependency verification) ──

    # Redis check (if URL configured)
    effective_redis_url = redis_url or os.environ.get("REDIS_URL")
    if effective_redis_url:
        aggregator.register_readiness_check(
            "redis",
            lambda url=effective_redis_url: check_redis(url),
        )

    # PostgreSQL check (if URL configured)
    effective_db_url = database_url or os.environ.get("DATABASE_URL")
    if effective_db_url:
        aggregator.register_readiness_check(
            "postgresql",
            lambda url=effective_db_url: check_postgresql(url),
        )

    # Circuit breaker check (if registry provided)
    if breaker_registry:
        aggregator.register_readiness_check(
            "circuit_breakers",
            lambda reg=breaker_registry: check_circuit_breakers(reg),
        )

    # Vector store check (Phase 4.1: if DATABASE_URL is PostgreSQL)
    effective_db_url = database_url or os.environ.get("DATABASE_URL")
    if effective_db_url and (
        effective_db_url.startswith("postgresql://") or
        effective_db_url.startswith("postgres://")
    ):
        aggregator.register_readiness_check(
            "vector_store",
            lambda: check_vector_store(),
        )

    logger.debug(
        f"Registered default checks: "
        f"liveness={list(aggregator._liveness_checks.keys())}, "
        f"readiness={list(aggregator._readiness_checks.keys())}"
    )


# ── Singleton ─────────────────────────────────────────────
_health_aggregator: Optional[HealthAggregator] = None
_health_lock = threading.Lock()


def get_health_aggregator(
    check_timeout: float = 5.0,
) -> HealthAggregator:
    """Get or create the singleton HealthAggregator.

    Phase 3.4: The singleton now auto-registers default checks
    based on environment variables on first creation.

    Args:
        check_timeout: Timeout per health check in seconds.

    Returns:
        The global HealthAggregator instance.
    """
    global _health_aggregator
    with _health_lock:
        if _health_aggregator is None:
            _health_aggregator = HealthAggregator(check_timeout=check_timeout)
            # Phase 3.4: Auto-register checks based on environment
            register_default_checks(_health_aggregator)
        return _health_aggregator
