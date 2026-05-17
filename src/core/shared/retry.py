"""
ZENIC-AGENTS — Shared Retry Utility.

NOTE: This is the simple procedural retry. For the RetryConfig-based version
used by the server/circuit-breaker, see src.core.patterns.resilience.retry.
For the v18 agent decorator version, see src.core.agents.resilience.retry.

Eliminates duplicated retry-with-exponential-backoff patterns across
all engine modules. Every engine had its own copy of the same retry loop;
this module provides a single source of truth.

Usage:
    from src.core.shared.retry import with_retry

    result = with_retry(
        fn=lambda: conn.execute("SELECT ..."),  # nosemgrep: sqlalchemy-execute-raw-query
        max_retries=3,
        base_delay=0.1,
        label="GraphAST store_node",
    )
"""

import time
import logging
from typing import TypeVar, Callable, Optional

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default retry constants
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 0.1  # 100ms

__all__ = [
    "DEFAULT_BASE_DELAY",
    "DEFAULT_MAX_RETRIES",
    "with_retry",
    "with_retry_or_false",
]


def with_retry(
    fn: Callable[[], T],
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    label: str = "operation",
    on_final_failure: Optional[Callable[[Exception], None]] = None,
) -> T:
    """Execute fn with retry and exponential backoff.

    Args:
        fn: The callable to execute. Called once per attempt.
        max_retries: Maximum number of attempts (default 3).
        base_delay: Base delay in seconds; doubles each retry (default 0.1).
        label: Descriptive label for log messages.
        on_final_failure: Optional callback if all retries fail.
            Receives the last exception. If not provided, the exception
            is re-raised.

    Returns:
        The return value of fn() on success.

    Raises:
        Exception: Re-raises the last exception if all retries fail
            and on_final_failure is not provided.
    """
    last_exception: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                logger.debug(
                    "%s error (attempt %d/%d): %s — retrying in %.2fs",
                    label, attempt, max_retries, e, delay,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "%s failed after %d attempts: %s", label, max_retries, e,
                )

    # All retries exhausted
    if on_final_failure is not None:
        on_final_failure(last_exception)
        # If callback doesn't raise, we need a return value — but this
        # should not normally happen. Return None as last resort.
        return None  # type: ignore[return-value]
    else:
        raise last_exception  # type: ignore[misc]


def with_retry_or_false(
    fn: Callable[[], T],
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    label: str = "operation",
) -> bool:
    """Execute fn with retry, returning True on success, False on all failures.

    Convenience wrapper for operations that don't need to return a value
    but need a success/failure indicator (e.g., DB writes).

    Args:
        fn: The callable to execute.
        max_retries: Maximum number of attempts.
        base_delay: Base delay in seconds.
        label: Descriptive label for log messages.

    Returns:
        True if fn() succeeded, False if all retries failed.
    """
    try:
        with_retry(fn, max_retries=max_retries, base_delay=base_delay, label=label)
        return True
    except Exception:
        return False
