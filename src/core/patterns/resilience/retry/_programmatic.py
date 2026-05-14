"""
ZENIC-AGENTS - Retry Pattern v16: Programmatic Retry Functions

with_retry (sync) and with_retry_async (async) functions.
"""

import asyncio
import logging
from typing import Any, Callable, Optional

from ._config import RetryConfig, _compute_delay

logger = logging.getLogger(__name__)


def with_retry(
    func: Callable[..., Any],
    config: RetryConfig,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Execute *func* with retry logic according to *config*.

    Args:
        func: Synchronous callable to execute.
        config: Retry configuration.
        *args: Positional arguments forwarded to *func*.
        **kwargs: Keyword arguments forwarded to *func*.

    Returns:
        The return value of *func* on success.

    Raises:
        The last exception encountered after all attempts are exhausted.
    """
    import time

    last_exception: Optional[Exception] = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except config.retryable_exceptions as exc:
            last_exception = exc
            if attempt >= config.max_attempts:
                logger.error(
                    "Retry exhausted for %s after %d attempts: %s",
                    getattr(func, "__name__", repr(func)),
                    attempt,
                    exc,
                )
                raise

            delay = _compute_delay(config, attempt)

            if config.on_retry is not None:
                try:
                    config.on_retry(attempt, exc, delay)
                except Exception as callback_err:
                    logger.warning(
                        "on_retry callback error: %s", callback_err,
                    )

            logger.info(
                "Retry %d/%d for %s after %.2fs: %s",
                attempt,
                config.max_attempts,
                getattr(func, "__name__", repr(func)),
                delay,
                exc,
            )
            time.sleep(delay)

    # Should be unreachable, but for type-safety:
    if last_exception is not None:
        raise last_exception
    raise RuntimeError("with_retry: unreachable state")


# Alias: prefer ``with_config_retry`` to distinguish from
# ``src.core.shared.retry.with_retry`` (simple procedural retry)
# and ``src.core.agents_v2.resilience.with_agent_retry`` (decorator-style).
with_config_retry = with_retry


async def with_retry_async(
    func: Callable[..., Any],
    config: RetryConfig,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Execute an async *func* with retry logic according to *config*.

    Args:
        func: Asynchronous callable to execute.
        config: Retry configuration.
        *args: Positional arguments forwarded to *func*.
        **kwargs: Keyword arguments forwarded to *func*.

    Returns:
        The return value of *func* on success.

    Raises:
        The last exception encountered after all attempts are exhausted.
    """
    last_exception: Optional[Exception] = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except config.retryable_exceptions as exc:
            last_exception = exc
            if attempt >= config.max_attempts:
                logger.error(
                    "Retry exhausted for %s after %d attempts: %s",
                    getattr(func, "__name__", repr(func)),
                    attempt,
                    exc,
                )
                raise

            delay = _compute_delay(config, attempt)

            if config.on_retry is not None:
                try:
                    config.on_retry(attempt, exc, delay)
                except Exception as callback_err:
                    logger.warning(
                        "on_retry callback error: %s", callback_err,
                    )

            logger.info(
                "Retry %d/%d for %s after %.2fs: %s",
                attempt,
                config.max_attempts,
                getattr(func, "__name__", repr(func)),
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    if last_exception is not None:
        raise last_exception
    raise RuntimeError("with_retry_async: unreachable state")
