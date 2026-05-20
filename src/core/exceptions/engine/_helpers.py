"""Helpers for engine."""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def _retry_db(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Execute *fn* with exponential-backoff retry on DB errors.

    The retry constants (_MAX_RETRIES, _BASE_DELAY) are imported lazily
    from ._types to avoid circular-import issues at module load time.
    """
    from ._types import _MAX_RETRIES, _BASE_DELAY  # noqa: F811

    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except sqlite3.OperationalError as exc:
            last_exc = exc
            delay = _BASE_DELAY * (2 ** attempt)
            logger.warning(
                "ExceptionEngine: DB retry %d/%d after %.2fs – %s",
                attempt + 1, _MAX_RETRIES, delay, exc,
            )
            time.sleep(delay)
        except sqlite3.Error as exc:
            last_exc = exc
            delay = _BASE_DELAY * (2 ** attempt)
            logger.warning(
                "ExceptionEngine: DB error retry %d/%d – %s",
                attempt + 1, _MAX_RETRIES, exc,
            )
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc  # type: ignore[misc]
