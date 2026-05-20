"""ZENIC-AGENTS - Impact Preview Engine: Retry Helper"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _retry_db_operation(
    func: Any,
    max_retries: int = 3,
    base_delay: float = 0.5,
) -> Any:
    """Execute a function with retry logic for DB operations.

    Args:
        func: Callable to execute.
        max_retries: Maximum number of retries.
        base_delay: Base delay in seconds for exponential backoff.

    Returns:
        The result of the function call.

    Raises:
        The last exception if all retries fail.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "ImpactPreviewEngine: DB retry %d/%d after %.2fs — %s",
                attempt + 1, max_retries, delay, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
        except Exception as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "ImpactPreviewEngine: Unexpected error on retry %d/%d — %s",
                attempt + 1, max_retries, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────
#  IMPACT PREVIEW ENGINE
# ──────────────────────────────────────────────────────────────
