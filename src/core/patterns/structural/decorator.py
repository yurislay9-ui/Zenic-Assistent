"""
ZENIC-AGENTS - Structural Pattern: Decorator

Composable capability decorators for agent execute/process methods.
Capabilities: logging, metrics, retry, circuit breaker, thermal limit,
timing, and rate limiting.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
"""

import enum
import functools
import logging
import random
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ======================================================================
# Capability enum
# ======================================================================

class AgentCapability(enum.Flag):
    """Capabilities that can be attached to agent methods via decorators."""
    LOGGING = enum.auto()
    METRICS = enum.auto()
    RETRY = enum.auto()
    CIRCUIT_BREAKER = enum.auto()
    THERMAL_LIMIT = enum.auto()
    TIMING = enum.auto()
    RATE_LIMIT = enum.auto()


# ======================================================================
# Internal helpers
# ======================================================================

class _CircuitBreakerState:
    """Minimal circuit breaker: CLOSED → OPEN → HALF_OPEN → CLOSED."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = self.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0.0
        self.lock = threading.Lock()

    def record_success(self) -> None:
        with self.lock:
            self.failure_count = 0
            self.state = self.CLOSED

    def record_failure(self) -> None:
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()
            if self.failure_count >= self.failure_threshold:
                self.state = self.OPEN

    def allow_request(self) -> bool:
        with self.lock:
            if self.state == self.CLOSED:
                return True
            if self.state == self.OPEN:
                if (time.monotonic() - self.last_failure_time) >= self.recovery_timeout:
                    self.state = self.HALF_OPEN
                    return True
                return False
            # HALF_OPEN
            return True


class _RateLimiter:
    """Simple token-bucket rate limiter."""

    def __init__(self, max_calls: int = 10, period: float = 1.0) -> None:
        self.max_calls = max_calls
        self.period = period
        self.tokens = max_calls
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self) -> bool:
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.max_calls, self.tokens + elapsed * (self.max_calls / self.period))
            self.last_refill = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


class _MetricsTracker:
    """Thread-safe metrics for a decorated method."""

    def __init__(self) -> None:
        self.call_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.total_duration = 0.0
        self.lock = threading.Lock()

    def record(self, duration: float, success: bool) -> None:
        with self.lock:
            self.call_count += 1
            self.total_duration += duration
            if success:
                self.success_count += 1
            else:
                self.failure_count += 1

    @property
    def stats(self) -> Dict[str, Any]:
        with self.lock:
            avg = self.total_duration / max(self.call_count, 1)
            return {
                "call_count": self.call_count,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "avg_duration": avg,
                "total_duration": self.total_duration,
            }


# ======================================================================
# Shared registries (one per decorated method for isolation)
# ======================================================================

_cb_registry: Dict[str, _CircuitBreakerState] = {}
_rl_registry: Dict[str, _RateLimiter] = {}
_metrics_registry: Dict[str, _MetricsTracker] = {}
_registry_lock = threading.Lock()


def _get_cb(key: str, config: dict) -> _CircuitBreakerState:
    with _registry_lock:
        if key not in _cb_registry:
            _cb_registry[key] = _CircuitBreakerState(
                failure_threshold=config.get("cb_failure_threshold", 5),
                recovery_timeout=config.get("cb_recovery_timeout", 30.0),
            )
        return _cb_registry[key]


def _get_rl(key: str, config: dict) -> _RateLimiter:
    with _registry_lock:
        if key not in _rl_registry:
            _rl_registry[key] = _RateLimiter(
                max_calls=config.get("rl_max_calls", 10),
                period=config.get("rl_period", 1.0),
            )
        return _rl_registry[key]


def _get_metrics(key: str) -> _MetricsTracker:
    with _registry_lock:
        if key not in _metrics_registry:
            _metrics_registry[key] = _MetricsTracker()
        return _metrics_registry[key]


# ======================================================================
# Decorator factory
# ======================================================================

def agent_decorator(
    *capabilities: AgentCapability,
    config: Optional[Dict[str, Any]] = None,
) -> Callable[..., Any]:
    """
    Return a decorator that wraps a function (typically an agent's
    ``execute`` or ``process`` method) with the requested capabilities.

    Args:
        *capabilities: One or more :class:`AgentCapability` flags.
        config: Optional configuration dict.  Recognised keys:

                - ``retry_max_attempts`` (int, default 3)
                - ``retry_delay`` (float, default 1.0)
                - ``retry_backoff`` (float, default 2.0)
                - ``cb_failure_threshold`` (int, default 5)
                - ``cb_recovery_timeout`` (float, default 30.0)
                - ``thermal_max`` (float, default 80.0) — CPU temp °C
                - ``rl_max_calls`` (int, default 10)
                - ``rl_period`` (float, default 1.0)
                - ``logger_name`` (str)

    Returns:
        A decorator function.

    Usage::

        @agent_decorator(AgentCapability.LOGGING, AgentCapability.RETRY,
                         config={"retry_max_attempts": 5})
        def execute(self, *args, **kwargs):
            ...
    """
    caps: AgentCapability = AgentCapability(0)
    for cap in capabilities:
        caps |= cap

    cfg = config or {}

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        key = f"{fn.__qualname__}"

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # ---- RATE_LIMIT ----
            if AgentCapability.RATE_LIMIT in caps:
                rl = _get_rl(key, cfg)
                if not rl.acquire():
                    raise RuntimeError(f"Rate limit exceeded for {key}")

            # ---- CIRCUIT_BREAKER (pre-check) ----
            if AgentCapability.CIRCUIT_BREAKER in caps:
                cb = _get_cb(key, cfg)
                if not cb.allow_request():
                    raise RuntimeError(f"Circuit breaker OPEN for {key}")

            # ---- THERMAL_LIMIT ----
            if AgentCapability.THERMAL_LIMIT in caps:
                # Best-effort thermal check (Linux /sys/class/thermal)
                _check_thermal(cfg.get("thermal_max", 80.0))

            # ---- LOGGING (pre) ----
            log = logger.getChild(cfg.get("logger_name", "agent_decorator"))
            if AgentCapability.LOGGING in caps:
                log.info("→ %s invoked", key)

            # ---- TIMING ----
            start = time.monotonic() if (AgentCapability.TIMING in caps or
                                         AgentCapability.METRICS in caps or
                                         AgentCapability.LOGGING in caps) else 0.0

            # ---- Execute with optional RETRY ----
            last_exc: Optional[Exception] = None
            max_attempts = cfg.get("retry_max_attempts", 3) if AgentCapability.RETRY in caps else 1
            delay = cfg.get("retry_delay", 1.0)
            backoff = cfg.get("retry_backoff", 2.0)

            result: Any = None
            success = False
            for attempt in range(1, max_attempts + 1):
                try:
                    result = fn(*args, **kwargs)
                    success = True
                    break
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_attempts:
                        current_delay = delay * (backoff ** (attempt - 1))
                        # Add jitter
                        current_delay *= (0.5 + random.random())
                        log.warning(
                            "↻ %s attempt %d/%d failed: %s – retrying in %.1fs",
                            key, attempt, max_attempts, exc, current_delay,
                        )
                        time.sleep(current_delay)

            elapsed = time.monotonic() - start if start else 0.0

            # ---- CIRCUIT_BREAKER (post) ----
            if AgentCapability.CIRCUIT_BREAKER in caps:
                cb = _get_cb(key, cfg)
                if success:
                    cb.record_success()
                else:
                    cb.record_failure()

            # ---- METRICS ----
            if AgentCapability.METRICS in caps:
                _get_metrics(key).record(elapsed, success)

            # ---- LOGGING (post) ----
            if AgentCapability.LOGGING in caps:
                if success:
                    log.info("← %s completed in %.3fs", key, elapsed)
                else:
                    log.error("← %s FAILED after %d attempts in %.3fs: %s",
                              key, max_attempts, elapsed, last_exc)

            # ---- TIMING (inject context) ----
            if AgentCapability.TIMING in caps and isinstance(result, dict):
                result = dict(result)
                result["_timing"] = {"elapsed_s": elapsed, "attempts": min(attempt, max_attempts)}

            if not success and last_exc is not None:
                raise last_exc

            return result

        # Attach introspection helpers
        wrapper._decorator_capabilities = caps  # type: ignore[attr-defined]
        wrapper._decorator_config = cfg  # type: ignore[attr-defined]

        return wrapper

    return decorator


# ======================================================================
# Thermal helper
# ======================================================================

def _check_thermal(max_temp: float) -> None:
    """
    Best-effort CPU temperature check on Linux.

    Raises :class:`RuntimeError` if temperature exceeds *max_temp*.
    Silently passes if temperature cannot be read (non-Linux, no sensor).
    """
    try:
        # Try common Linux thermal zone
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_c = int(f.read().strip()) / 1000.0
        if temp_c > max_temp:
            raise RuntimeError(
                f"Thermal limit exceeded: {temp_c:.1f}°C > {max_temp:.1f}°C"
            )
    except (FileNotFoundError, PermissionError, ValueError):
        pass  # Not available – skip check


# ======================================================================
# AgentDecorator (composable)
# ======================================================================

class AgentDecorator:
    """
    Composable wrapper for applying multiple capability decorators to a
    single function in a clean, ordered fashion.

    Usage::

        decorated = (
            AgentDecorator()
            .add(AgentCapability.LOGGING)
            .add(AgentCapability.RETRY, config={"retry_max_attempts": 5})
            .apply(my_agent.execute)
        )
    """

    def __init__(self) -> None:
        self._layers: List[Tuple[AgentCapability, Dict[str, Any]]] = []

    def add(
        self,
        capability: AgentCapability,
        config: Optional[Dict[str, Any]] = None,
    ) -> "AgentDecorator":
        """Add a capability layer (applied in FIFO order)."""
        self._layers.append((capability, config or {}))
        return self

    def apply(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """
        Apply all registered capability layers to *fn*.

        Layers are applied **in reverse order** so that the first added
        capability is the outermost wrapper.
        """
        wrapped = fn
        for cap, cfg in reversed(self._layers):
            wrapped = agent_decorator(cap, config=cfg)(wrapped)
        return wrapped
