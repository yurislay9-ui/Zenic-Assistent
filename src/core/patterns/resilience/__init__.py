"""
ZENIC-AGENTS - Resilience Patterns v16

Facade module — re-exports all resilience pattern components
from sub-modules for convenient single-point imports.

Usage::

    from src.core.patterns.resilience import (
        CircuitBreaker, CircuitState, CircuitOpenError,
        RetryConfig, retry, retry_async, with_retry,
        Bulkhead, BulkheadFullError,
        Sidecar, sidecar_decorator,
    )

Designed for Android/Termux (500MB RAM) — stdlib only.
"""

from .circuit_breaker import CircuitBreaker, CircuitState, CircuitOpenError
from .retry import RetryConfig, retry, retry_async, with_retry, with_retry_async, RetryScope
from .bulkhead import Bulkhead, BulkheadFullError
from .sidecar import Sidecar, sidecar_decorator

__all__ = [
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitState",
    "CircuitOpenError",
    # Retry
    "RetryConfig",
    "retry",
    "retry_async",
    "with_retry",
    "with_retry_async",
    "RetryScope",
    # Bulkhead
    "Bulkhead",
    "BulkheadFullError",
    # Sidecar
    "Sidecar",
    "sidecar_decorator",
]
