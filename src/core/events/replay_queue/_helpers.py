"""Helper methods extracted from replay_queue."""

from __future__ import annotations

import json
import sqlite3
from ._types import DeadLetterEvent, DeadLetterStatus, DEFAULT_MAX_RETRIES

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


    def _init_db(self) -> None:
        """Initialize the SQLite database."""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS dead_letter_events (
                    dlq_id          TEXT PRIMARY KEY,
                    event_type      TEXT NOT NULL,
                    event_data_json TEXT NOT NULL DEFAULT '{}',
                    error           TEXT NOT NULL DEFAULT '',
                    tenant_id       TEXT NOT NULL,
                    retry_count     INTEGER NOT NULL DEFAULT 0,
                    max_retries     INTEGER NOT NULL DEFAULT 3,
                    last_retry_at   REAL NOT NULL DEFAULT 0.0,
                    created_at      REAL NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'pending'
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_dlq_tenant_status
                ON dead_letter_events(tenant_id, status)
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_dlq_status
                ON dead_letter_events(status)
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_dlq_created
                ON dead_letter_events(created_at)
            """)
            conn.commit()
        finally:
            conn.close()
        self._initialized = True


    def _load_from_db(self) -> None:
        """Load all events from SQLite into memory."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM dead_letter_events"
            ).fetchall()
            with self._lock:
                for row in rows:
                    evt = _event_from_row(row)
                    self._events[evt.dlq_id] = evt
        finally:
            conn.close()
        logger.info(
            "ReplayQueue: loaded %d events from %s",
            len(self._events), self._db_path,
        )


    def _persist_event(self, evt: DeadLetterEvent) -> None:
        """Write or update an event in SQLite."""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                INSERT OR REPLACE INTO dead_letter_events
                    (dlq_id, event_type, event_data_json, error, tenant_id,
                     retry_count, max_retries, last_retry_at, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evt.dlq_id,
                    evt.event_type,
                    json.dumps(evt.event_data),
                    evt.error,
                    evt.tenant_id,
                    evt.retry_count,
                    evt.max_retries,
                    evt.last_retry_at,
                    evt.created_at,
                    evt.status.value,
                ),
            )
            conn.commit()
        finally:
            conn.close()


    def _delete_event(self, dlq_id: str) -> None:
        """Delete an event from SQLite."""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "DELETE FROM dead_letter_events WHERE dlq_id = ?",
                (dlq_id,),
            )
            conn.commit()
        finally:
            conn.close()

    # ── Enqueue ─────────────────────────────────────────────────

