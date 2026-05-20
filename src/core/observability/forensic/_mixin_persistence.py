"""
forensic._mixin_persistence — Persistence helpers mixin for ForensicEngine.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Optional, Tuple

from src.core.observability.forensic._helpers import retry as _retry

logger = logging.getLogger(__name__)


class PersistenceMixin:
    """Mixin providing query persistence helpers for ForensicEngine."""

    # These attributes are provided by the main class.
    _db_path: str
    _lock: object
    _initialized: bool

    def _record_query(
        self,
        query_id: str,
        query_type: str,
        entity_id: str,
        tenant_id: str,
        time_range: Optional[Tuple[float, float]],
        result_summary: str,
    ) -> None:
        """Persist a record of a forensic query to SQLite."""
        if not self._initialized:
            return

        def _insert() -> None:
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT INTO forensic_queries
                       (query_id, query_type, entity_id, tenant_id,
                        time_range_start, time_range_end, result_summary, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        query_id,
                        query_type,
                        entity_id,
                        tenant_id,
                        time_range[0] if time_range else None,
                        time_range[1] if time_range else None,
                        result_summary,
                        time.time(),
                    ),
                )
                conn.commit()
                conn.close()

        try:
            _retry(_insert, label="ForensicEngine._record_query")
        except Exception as exc:
            logger.error("ForensicEngine: failed to record query: %s", exc)
