"""
Batch Approval Engine — Persistence Mixin.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any, List, Optional

from ._types import BatchRequest, _MAX_RETRIES, _RETRY_DELAY

logger = logging.getLogger(__name__)


class BatchPersistenceMixin:
    """Persistence helpers for BatchApprovalEngine."""

    # ── DB Initialisation ──────────────────────────────────

    def _init_db(self) -> None:
        """Create the batch_requests table if it does not exist."""
        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS batch_requests (
                    batch_id TEXT PRIMARY KEY,
                    action_type TEXT NOT NULL,
                    action_configs TEXT NOT NULL,
                    requested_by INTEGER NOT NULL,
                    required_role TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    total_count INTEGER NOT NULL DEFAULT 0,
                    approved_count INTEGER NOT NULL DEFAULT 0,
                    rejected_count INTEGER NOT NULL DEFAULT 0,
                    request_ids TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_batch_status
                ON batch_requests(status, created_at DESC)
            """)
            conn.commit()
            conn.close()

        self._with_retry(_do_init)

    # ── Private Helpers ────────────────────────────────────

    def _get_batch_internal(self, batch_id: str) -> Optional[BatchRequest]:
        """Retrieve a batch from the database."""
        def _do_find() -> Optional[BatchRequest]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM batch_requests WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return self._row_to_batch(row)

        return self._with_retry(_do_find, fallback=None)

    def _persist_batch(self, batch: BatchRequest, *, insert: bool) -> None:
        """Insert or update a batch in the database."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            if insert:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT INTO batch_requests
                       (batch_id, action_type, action_configs, requested_by,
                        required_role, status, total_count, approved_count,
                        rejected_count, request_ids, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        batch.batch_id, batch.action_type,
                        json.dumps(batch.action_configs),
                        batch.requested_by, batch.required_role,
                        batch.status, batch.total_count,
                        batch.approved_count, batch.rejected_count,
                        json.dumps(batch.request_ids),
                        batch.created_at,
                    ),
                )
            else:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """UPDATE batch_requests SET
                       status=?, approved_count=?, rejected_count=?, request_ids=?
                       WHERE batch_id=?""",
                    (
                        batch.status, batch.approved_count,
                        batch.rejected_count, json.dumps(batch.request_ids),
                        batch.batch_id,
                    ),
                )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)

    @staticmethod
    def _row_to_batch(row: sqlite3.Row) -> BatchRequest:
        """Convert a database row to a BatchRequest."""
        return BatchRequest(
            batch_id=row["batch_id"],
            action_type=row["action_type"],
            action_configs=json.loads(row["action_configs"] or "[]"),
            requested_by=row["requested_by"],
            required_role=row["required_role"],
            status=row["status"],
            total_count=row["total_count"],
            approved_count=row["approved_count"],
            rejected_count=row["rejected_count"],
            request_ids=json.loads(row["request_ids"] or "[]"),
            created_at=row["created_at"],
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
                    "BatchApproval: DB retry %d/%d — %s", attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    time.sleep(_RETRY_DELAY * attempt)
            except Exception as exc:
                last_exc = exc
                logger.error("BatchApproval: DB error — %s", exc)
                break
        logger.error("BatchApproval: All retries exhausted — %s", last_exc)
        return fallback
