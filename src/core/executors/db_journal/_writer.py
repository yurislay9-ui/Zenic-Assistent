"""
ZENIC-AGENTS - DB Journal Writer Mixin

Write / persist methods for the DB Transaction Journal, including
schema initialisation and before-state capture.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from src.core.shared.retry import with_retry
from src.core.shared.db_initializer import get_data_dir

from ._types import JournalEntry
from ._sql_helpers import (
    _extract_table_and_where_from_delete,
    _extract_table_and_where_from_update,
    _extract_set_clause_from_update,
    _count_placeholders,
)

logger = logging.getLogger(__name__)


class _WriterMixin:
    """Write and persist methods for DBTransactionJournal."""

    _JOURNAL_DB_NAME = "db_journal.sqlite"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._db_path = str(get_data_dir() / self._JOURNAL_DB_NAME)
        self._init_db()

    # ── Schema initialisation ────────────────────────────────

    def _init_db(self) -> None:
        """Create the journal SQLite table if it does not exist."""

        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """
                    CREATE TABLE IF NOT EXISTS journal_entries (
                        journal_id   TEXT PRIMARY KEY,
                        db_path      TEXT NOT NULL,
                        operation    TEXT NOT NULL,
                        query        TEXT NOT NULL,
                        params       TEXT NOT NULL DEFAULT '[]',
                        before_data  TEXT NOT NULL DEFAULT '[]',
                        after_data   TEXT NOT NULL DEFAULT '[]',
                        affected_rows INTEGER NOT NULL DEFAULT 0,
                        lastrowid    INTEGER,
                        tenant_id    TEXT NOT NULL,
                        created_at   REAL NOT NULL,
                        rolled_back  INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "CREATE INDEX IF NOT EXISTS idx_je_db_tenant "
                    "ON journal_entries(db_path, tenant_id)"
                )
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "CREATE INDEX IF NOT EXISTS idx_je_tenant "
                    "ON journal_entries(tenant_id)"
                )
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "CREATE INDEX IF NOT EXISTS idx_je_created "
                    "ON journal_entries(created_at)"
                )
                conn.commit()
            finally:
                conn.close()

        with_retry(_do_init, max_retries=3, base_delay=0.5, label="db_journal._init_db")
        logger.debug("DBTransactionJournal: schema initialised at %s", self._db_path)

    # ── Core public API ──────────────────────────────────────

    def journal_before(
        self,
        db_path: str,
        operation: str,
        query: str,
        params: List[Any],
        tenant_id: str,
    ) -> str:
        """Capture the current row state *before* a write operation.

        For DELETE / UPDATE the method executes a SELECT with the same
        WHERE clause to capture the rows that will be affected.  For
        INSERT it simply records that no prior data existed.

        Args:
            db_path: Path to the database that will be modified.
            operation: SQL operation type (INSERT, UPDATE, DELETE).
            query: The SQL query that will be executed.
            params: The query parameters.
            tenant_id: Tenant identifier for multi-tenancy.

        Returns:
            The ``journal_id`` of the created journal entry.
        """
        op = operation.strip().upper()
        entry = JournalEntry(
            db_path=db_path,
            operation=op,
            query=query,
            params=list(params),
            tenant_id=tenant_id,
        )

        # Capture before-state
        before_data: List[Dict[str, Any]] = []
        if op in ("DELETE", "UPDATE"):
            before_data = self._capture_before_state(db_path, op, query, params)
        # For INSERT, before_data stays [] (no prior data existed)

        entry.before_data = json.dumps(before_data, default=str)

        # Persist the journal entry
        self._persist_entry(entry)

        logger.info(
            "DBTransactionJournal: journal_before %s op=%s db=%s [tenant=%s]",
            entry.journal_id[:12], op, db_path, tenant_id,
        )
        return entry.journal_id

    def journal_after(
        self,
        journal_id: str,
        affected_rows: int,
        lastrowid: Optional[int],
    ) -> None:
        """Record the result *after* the write operation has executed.

        Args:
            journal_id: The journal entry to update.
            affected_rows: Number of rows affected by the write.
            lastrowid: The ``lastrowid`` from the cursor (may be None).
        """

        def _do_update() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """
                    UPDATE journal_entries
                    SET affected_rows = ?, lastrowid = ?
                    WHERE journal_id = ?
                    """,
                    (affected_rows, lastrowid, journal_id),
                )
                conn.commit()
            finally:
                conn.close()

        with_retry(
            _do_update,
            max_retries=3,
            base_delay=0.5,
            label=f"db_journal.journal_after({journal_id[:12]})",
        )
        logger.debug(
            "DBTransactionJournal: journal_after %s affected=%d lastrowid=%s",
            journal_id[:12], affected_rows, lastrowid,
        )

    # ── Before-state capture helpers ─────────────────────────

    def _capture_before_state(
        self,
        db_path: str,
        operation: str,
        query: str,
        params: List[Any],
    ) -> List[Dict[str, Any]]:
        """Execute a SELECT to capture affected rows before the write.

        For DELETE and UPDATE statements this constructs a SELECT query
        using the same WHERE clause as the original statement.
        """

        def _do_capture() -> List[Dict[str, Any]]:
            if db_path == ":memory:":
                # Cannot capture from in-memory DB in a different connection
                return []

            select_query = ""
            select_params: List[Any] = []

            if operation == "DELETE":
                table, where_clause = _extract_table_and_where_from_delete(query)
                if not table:
                    return []
                select_query = f"SELECT * FROM {table}"
                if where_clause:
                    select_query += f" WHERE {where_clause}"
                    select_params = list(params)
            elif operation == "UPDATE":
                table, where_clause = _extract_table_and_where_from_update(query)
                if not table:
                    return []
                select_query = f"SELECT * FROM {table}"
                if where_clause:
                    select_query += f" WHERE {where_clause}"
                    # For UPDATE, params correspond to SET values first, then WHERE values.
                    # We must skip the SET placeholders and use only the WHERE params.
                    set_clause = _extract_set_clause_from_update(query)
                    set_placeholders = _count_placeholders(set_clause)
                    select_params = list(params[set_placeholders:])
                else:
                    # No WHERE clause — select all rows, no params needed
                    select_params = []
            else:
                return []

            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                try:
                    cursor = conn.execute(select_query, select_params)  # nosemgrep: sqlalchemy-execute-raw-query
                    rows = [dict(row) for row in cursor.fetchall()]
                    return rows
                finally:
                    conn.close()
            except Exception as exc:
                logger.warning(
                    "DBTransactionJournal: failed to capture before-state for %s: %s",
                    operation, exc,
                )
                return []

        return with_retry(
            _do_capture,
            max_retries=3,
            base_delay=0.5,
            label=f"db_journal._capture_before_state({operation})",
        )

    # ── Persistence helpers ──────────────────────────────────

    def _persist_entry(self, entry: JournalEntry) -> None:
        """Write a JournalEntry to SQLite."""

        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """
                    INSERT INTO journal_entries
                        (journal_id, db_path, operation, query, params,
                         before_data, after_data, affected_rows, lastrowid,
                         tenant_id, created_at, rolled_back)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.journal_id,
                        entry.db_path,
                        entry.operation,
                        entry.query,
                        json.dumps(entry.params, default=str),
                        entry.before_data,
                        entry.after_data,
                        entry.affected_rows,
                        entry.lastrowid,
                        entry.tenant_id,
                        entry.created_at,
                        1 if entry.rolled_back else 0,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        with_retry(
            _do_persist,
            max_retries=3,
            base_delay=0.5,
            label=f"db_journal._persist_entry({entry.journal_id[:12]})",
        )

    def _mark_rolled_back(self, journal_id: str) -> None:
        """Mark a journal entry as having been rolled back."""

        def _do_mark() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "UPDATE journal_entries SET rolled_back = 1 WHERE journal_id = ?",
                    (journal_id,),
                )
                conn.commit()
            finally:
                conn.close()

        with_retry(
            _do_mark,
            max_retries=3,
            base_delay=0.5,
            label=f"db_journal._mark_rolled_back({journal_id[:12]})",
        )
