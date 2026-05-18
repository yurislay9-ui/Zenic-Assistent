"""
Expiry Manager — Persistence Mixin.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any, List, Optional

from ._types import ExpiryRecord, _MAX_RETRIES, _RETRY_DELAY

logger = logging.getLogger(__name__)


class ExpiryPersistenceMixin:
    """Persistence helpers for ExpiryManager."""

    # ── DB Initialisation ──────────────────────────────────

    def _init_db(self) -> None:
        """Create the expiry records table if it does not exist."""
        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS expiry_records (
                    request_id TEXT PRIMARY KEY,
                    expires_at TEXT NOT NULL,
                    reverted_at TEXT,
                    revert_result TEXT,
                    notification_sent_at TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'active'
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_expiry_status
                ON expiry_records(status, expires_at)
            """)
            conn.commit()
            conn.close()

        self._with_retry(_do_init)

    # ── Private Helpers ────────────────────────────────────

    def _get_active_records(self) -> List[ExpiryRecord]:
        """Get all active expiry records."""
        def _do_query() -> List[ExpiryRecord]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """SELECT * FROM expiry_records
                   WHERE status = 'active'
                   ORDER BY expires_at ASC""",
            ).fetchall()
            conn.close()
            return [self._row_to_expiry_record(r) for r in rows]

        return self._with_retry(_do_query, fallback=[])

    def _persist_expiry_record(
        self, record: ExpiryRecord, *, insert: bool,
    ) -> None:
        """Insert or update an expiry record."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            result_json = json.dumps(record.revert_result) if record.revert_result else None

            if insert:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT INTO expiry_records
                       (request_id, expires_at, reverted_at, revert_result,
                        notification_sent_at, status)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        record.request_id,
                        record.expires_at,
                        record.reverted_at,
                        result_json,
                        json.dumps(record.notification_sent_at),
                        record.status,
                    ),
                )
            else:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """UPDATE expiry_records SET
                       expires_at=?, reverted_at=?, revert_result=?,
                       notification_sent_at=?, status=?
                       WHERE request_id=?""",
                    (
                        record.expires_at,
                        record.reverted_at,
                        result_json,
                        json.dumps(record.notification_sent_at),
                        record.status,
                        record.request_id,
                    ),
                )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)

    @staticmethod
    def _row_to_expiry_record(row: sqlite3.Row) -> ExpiryRecord:
        """Convert a database row to an ExpiryRecord."""
        result_data = json.loads(row["revert_result"]) if row["revert_result"] else None
        return ExpiryRecord(
            request_id=row["request_id"],
            expires_at=row["expires_at"],
            reverted_at=row["reverted_at"],
            revert_result=result_data,
            notification_sent_at=json.loads(row["notification_sent_at"] or "[]"),
            status=row["status"],
        )

    @staticmethod
    def _with_retry(
        fn: Any,
        fallback: Any = None,
        max_retries: int = _MAX_RETRIES,
    ) -> Any:
        """Execute *fn* with retry logic on database errors."""
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                return fn()
            except sqlite3.OperationalError as exc:
                last_exc = exc
                logger.warning(
                    "ExpiryManager: DB retry %d/%d — %s",
                    attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    time.sleep(_RETRY_DELAY * attempt)
            except Exception as exc:
                last_exc = exc
                logger.error("ExpiryManager: DB error — %s", exc)
                break
        logger.error("ExpiryManager: All retries exhausted — %s", last_exc)
        return fallback
