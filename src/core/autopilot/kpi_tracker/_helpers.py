"""
KPI Tracker — Database helpers and retry logic.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any, Optional

from ._types import KPIMeasurement

logger = logging.getLogger(__name__)


def retry_db_operation(
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
                "KPITracker: DB retry %d/%d after %.2fs — %s",
                attempt + 1, max_retries, delay, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
        except Exception as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "KPITracker: Unexpected error on retry %d/%d — %s",
                attempt + 1, max_retries, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def row_to_measurement(row: sqlite3.Row) -> KPIMeasurement:
    """Convert a database row to a KPIMeasurement instance."""
    return KPIMeasurement(
        measurement_id=row["measurement_id"],
        objective_id=row["objective_id"],
        metric_name=row["metric_name"],
        value=row["value"],
        target_value=row["target_value"],
        unit=row["unit"],
        timestamp=row["timestamp"],
        source=row["source"],
        delta_from_last=row["delta_from_last"],
    )
