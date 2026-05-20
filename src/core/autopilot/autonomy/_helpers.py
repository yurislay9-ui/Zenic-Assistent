"""Helpers for autonomy."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def _retry_db_operation(
    func: Any,
    max_retries: int = 3,
    base_delay: float = 0.5,
) -> Any:
    """Retry a database operation with exponential backoff.

    Args:
        func: A callable that performs the DB operation.
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds for exponential backoff.

    Returns:
        The return value of *func* on success.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "DB operation failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    max_retries + 1,
                    delay,
                    exc,
                )
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]
