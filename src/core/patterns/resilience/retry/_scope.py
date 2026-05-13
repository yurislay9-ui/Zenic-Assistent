"""
ZENIC-AGENTS - Retry Pattern v16: Decorators and RetryScope

retry/retry_async decorators and RetryScope context manager.
"""

import functools
import logging
from typing import Any, Callable, Optional

from ._config import RetryConfig
from ._programmatic import with_retry, with_retry_async

logger = logging.getLogger(__name__)


def retry(config: Optional[RetryConfig] = None) -> Callable[..., Any]:
    """
    Decorator for synchronous functions with retry logic.

    Usage::

        @retry(RetryConfig(max_attempts=5))
        def flaky_operation():
            ...

        @retry()  # uses default RetryConfig
        def another_flaky():
            ...
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return with_retry(func, config, *args, **kwargs)
        return wrapper
    return decorator


def retry_async(config: Optional[RetryConfig] = None) -> Callable[..., Any]:
    """
    Decorator for asynchronous functions with retry logic.

    Usage::

        @retry_async(RetryConfig(max_attempts=5))
        async def flaky_async():
            ...
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await with_retry_async(func, config, *args, **kwargs)
        return wrapper
    return decorator


class RetryScope:
    """
    Context manager that provides a shared retry configuration for
    multiple operations.

    Usage::

        with RetryScope(RetryConfig(max_attempts=3)) as scope:
            scope.execute(flaky_func, arg1, arg2)
            scope.execute(another_func, kwarg=42)

    The scope collects stats across all operations.
    """

    def __init__(self, config: Optional[RetryConfig] = None) -> None:
        self._config = config or RetryConfig()
        self._total_operations: int = 0
        self._total_retries: int = 0
        self._total_failures: int = 0

    # ----------------------------------------------------------
    #  Context manager protocol
    # ----------------------------------------------------------

    def __enter__(self) -> "RetryScope":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        logger.debug(
            "RetryScope exiting: %d operations, %d retries, %d failures",
            self._total_operations,
            self._total_retries,
            self._total_failures,
        )

    # ----------------------------------------------------------
    #  Execution
    # ----------------------------------------------------------

    def execute(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """Execute *func* within this scope's retry configuration."""
        self._total_operations += 1
        retry_count_holder = [0]

        original_on_retry = self._config.on_retry

        def counting_on_retry(
            attempt: int, exc: Exception, delay: float
        ) -> None:
            retry_count_holder[0] += 1
            self._total_retries += 1
            if original_on_retry is not None:
                original_on_retry(attempt, exc, delay)

        # Temporarily override on_retry to count retries
        saved_on_retry = self._config.on_retry
        self._config.on_retry = counting_on_retry
        try:
            result = with_retry(func, self._config, *args, **kwargs)
        except Exception:
            self._total_failures += 1
            raise
        finally:
            self._config.on_retry = saved_on_retry

        return result

    async def execute_async(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """Execute an async *func* within this scope's retry configuration."""
        self._total_operations += 1
        retry_count_holder = [0]

        original_on_retry = self._config.on_retry

        def counting_on_retry(
            attempt: int, exc: Exception, delay: float
        ) -> None:
            retry_count_holder[0] += 1
            self._total_retries += 1
            if original_on_retry is not None:
                original_on_retry(attempt, exc, delay)

        saved_on_retry = self._config.on_retry
        self._config.on_retry = counting_on_retry
        try:
            result = await with_retry_async(func, self._config, *args, **kwargs)
        except Exception:
            self._total_failures += 1
            raise
        finally:
            self._config.on_retry = saved_on_retry

        return result

    # ----------------------------------------------------------
    #  Stats
    # ----------------------------------------------------------

    @property
    def stats(self) -> dict:
        """Snapshot of scope statistics."""
        return {
            "total_operations": self._total_operations,
            "total_retries": self._total_retries,
            "total_failures": self._total_failures,
            "config": {
                "max_attempts": self._config.max_attempts,
                "backoff_strategy": self._config.backoff_strategy,
                "base_delay": self._config.base_delay,
                "max_delay": self._config.max_delay,
            },
        }

    def __repr__(self) -> str:
        return (
            f"RetryScope(ops={self._total_operations}, "
            f"retries={self._total_retries}, "
            f"failures={self._total_failures})"
        )
