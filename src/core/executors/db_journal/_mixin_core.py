"""
db_journal._mixin_core — Core public API and persistence mixin for DBTransactionJournal.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from src.core.shared.retry import with_retry
from src.core.shared.db_initializer import get_data_dir
from src.core.executors.db_journal._types import JournalEntry, RollbackResult
from src.core.executors.db_journal._helpers import (
    extract_table_and_where_from_delete,
    extract_table_and_where_from_update,
    extract_set_clause_from_update,
    count_placeholders,
)

logger = logging.getLogger(__name__)


class CoreMixin:
    """Mixin providing core public API and persistence for DBTransactionJournal."""

    # These attributes are provided by the main class.
    _db_path: str
    _lock: object

    _JOURNAL_DB_NAME: str = "db_journal.sqlite"

    # ── Schema initialisation ────────────────────────────────

    def _init_db(self) -> None:
        """Create the journal SQLite table if it does not exist."""

        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(  # nosemgrep
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
                conn.execute(  # nosemgrep
                    "CREATE INDEX IF NOT EXISTS idx_je_db_tenant "
                    "ON journal_entries(db_path, tenant_id)"
                )
                conn.execute(  # nosemgrep
                    "CREATE INDEX IF NOT EXISTS idx_je_tenant "
                    "ON journal_entries(tenant_id)"
                )
                conn.execute(  # nosemgrep
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
        self, db_path: str, operation: str, query: str,
        params: List[Any], tenant_id: str,
    ) -> str:
        """Capture the current row state *before* a write operation."""
        op = operation.strip().upper()
        entry = JournalEntry(
            db_path=db_path, operation=op, query=query,
            params=list(params), tenant_id=tenant_id,
        )

        before_data: List[Dict[str, Any]] = []
        if op in ("DELETE", "UPDATE"):
            before_data = self._capture_before_state(db_path, op, query, params)

        entry.before_data = json.dumps(before_data, default=str)
        self._persist_entry(entry)

        logger.info(
            "DBTransactionJournal: journal_before %s op=%s db=%s [tenant=%s]",
            entry.journal_id[:12], op, db_path, tenant_id,
        )
        return entry.journal_id

    def journal_after(
        self, journal_id: str, affected_rows: int,
        lastrowid: Optional[int],
    ) -> None:
        """Record the result *after* the write operation has executed."""

        def _do_update() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(  # nosemgrep
                    "UPDATE journal_entries SET affected_rows = ?, lastrowid = ? WHERE journal_id = ?",
                    (affected_rows, lastrowid, journal_id),
                )
                conn.commit()
            finally:
                conn.close()

        with_retry(
            _do_update, max_retries=3, base_delay=0.5,
            label=f"db_journal.journal_after({journal_id[:12]})",
        )

    def rollback_to(self, journal_id: str) -> RollbackResult:
        """Restore the exact state captured in the journal entry."""
        with self._lock:
            entry = self.get_journal(journal_id)
            if entry is None:
                return RollbackResult(
                    success=False, journal_id=journal_id,
                    errors=[f"Journal entry {journal_id} not found"],
                )

            if entry.rolled_back:
                return RollbackResult(
                    success=False, journal_id=journal_id,
                    operation=entry.operation,
                    errors=[f"Journal entry {journal_id} already rolled back"],
                )

            result = RollbackResult(
                journal_id=journal_id, operation=entry.operation,
            )

            try:
                if entry.operation == "DELETE":
                    result.rows_restored = self._rollback_delete(entry, result)
                elif entry.operation == "UPDATE":
                    result.rows_restored = self._rollback_update(entry, result)
                elif entry.operation == "INSERT":
                    result.rows_restored = self._rollback_insert(entry, result)
                else:
                    result.errors.append(
                        f"Unsupported operation for rollback: {entry.operation}"
                    )

                self._mark_rolled_back(journal_id)
                result.success = len(result.errors) == 0
                logger.info(
                    "DBTransactionJournal: rollback_to %s op=%s restored=%d success=%s",
                    journal_id[:12], entry.operation, result.rows_restored, result.success,
                )
            except Exception as exc:
                result.errors.append(str(exc))
                result.success = False
                logger.error(
                    "DBTransactionJournal: rollback_to %s FAILED: %s",
                    journal_id[:12], exc,
                )

            return result

    def get_journal(self, journal_id: str) -> Optional[JournalEntry]:
        """Retrieve a journal entry by its ID."""

        def _do_get() -> Optional[JournalEntry]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(  # nosemgrep
                    "SELECT * FROM journal_entries WHERE journal_id = ?",
                    (journal_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                return self._row_to_entry(row)
            finally:
                conn.close()

        return with_retry(
            _do_get, max_retries=3, base_delay=0.5,
            label=f"db_journal.get_journal({journal_id[:12]})",
        )

    def list_journals(
        self, db_path: str, tenant_id: str, limit: int = 100,
    ) -> List[JournalEntry]:
        """List journal entries for a specific database and tenant."""

        def _do_list() -> List[JournalEntry]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(  # nosemgrep
                    "SELECT * FROM journal_entries "
                    "WHERE db_path = ? AND tenant_id = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (db_path, tenant_id, limit),
                )
                return [self._row_to_entry(row) for row in cursor.fetchall()]
            finally:
                conn.close()

        return with_retry(
            _do_list, max_retries=3, base_delay=0.5,
            label="db_journal.list_journals",
        )

    def prune_journals(self, older_than_hours: int, tenant_id: str) -> int:
        """Delete journal entries older than the specified number of hours."""
        import time
        cutoff = time.time() - (older_than_hours * 3600)

        def _do_prune() -> int:
            conn = sqlite3.connect(self._db_path)
            try:
                cursor = conn.execute(  # nosemgrep
                    "DELETE FROM journal_entries "
                    "WHERE created_at < ? AND tenant_id = ? AND rolled_back = 0",
                    (cutoff, tenant_id),
                )
                conn.commit()
                deleted = cursor.rowcount
                logger.info(
                    "DBTransactionJournal: prune_journals deleted %d entries older than %dh [tenant=%s]",
                    deleted, older_than_hours, tenant_id,
                )
                return deleted
            finally:
                conn.close()

        return with_retry(
            _do_prune, max_retries=3, base_delay=0.5,
            label="db_journal.prune_journals",
        )

    # ── Before-state capture ──────────────────────────────────

    def _capture_before_state(
        self, db_path: str, operation: str,
        query: str, params: List[Any],
    ) -> List[Dict[str, Any]]:
        """Execute a SELECT to capture affected rows before the write."""

        def _do_capture() -> List[Dict[str, Any]]:
            if db_path == ":memory:":
                return []

            select_query = ""
            select_params: List[Any] = []

            if operation == "DELETE":
                table, where_clause = extract_table_and_where_from_delete(query)
                if not table:
                    return []
                select_query = f"SELECT * FROM {table}"
                if where_clause:
                    select_query += f" WHERE {where_clause}"
                    select_params = list(params)
            elif operation == "UPDATE":
                table, where_clause = extract_table_and_where_from_update(query)
                if not table:
                    return []
                select_query = f"SELECT * FROM {table}"
                if where_clause:
                    select_query += f" WHERE {where_clause}"
                    set_clause = extract_set_clause_from_update(query)
                    set_placeholders = count_placeholders(set_clause)
                    select_params = list(params[set_placeholders:])
                else:
                    select_params = []
            else:
                return []

            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                try:
                    cursor = conn.execute(select_query, select_params)  # nosemgrep
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
            _do_capture, max_retries=3, base_delay=0.5,
            label=f"db_journal._capture_before_state({operation})",
        )

    # ── Persistence helpers ──────────────────────────────────

    def _persist_entry(self, entry: JournalEntry) -> None:
        """Write a JournalEntry to SQLite."""

        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(  # nosemgrep
                    "INSERT INTO journal_entries "
                    "(journal_id, db_path, operation, query, params, "
                    "before_data, after_data, affected_rows, lastrowid, "
                    "tenant_id, created_at, rolled_back) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        entry.journal_id, entry.db_path, entry.operation,
                        entry.query, json.dumps(entry.params, default=str),
                        entry.before_data, entry.after_data,
                        entry.affected_rows, entry.lastrowid,
                        entry.tenant_id, entry.created_at,
                        1 if entry.rolled_back else 0,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        with_retry(
            _do_persist, max_retries=3, base_delay=0.5,
            label=f"db_journal._persist_entry({entry.journal_id[:12]})",
        )

    def _mark_rolled_back(self, journal_id: str) -> None:
        """Mark a journal entry as having been rolled back."""

        def _do_mark() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(  # nosemgrep
                    "UPDATE journal_entries SET rolled_back = 1 WHERE journal_id = ?",
                    (journal_id,),
                )
                conn.commit()
            finally:
                conn.close()

        with_retry(
            _do_mark, max_retries=3, base_delay=0.5,
            label=f"db_journal._mark_rolled_back({journal_id[:12]})",
        )

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> JournalEntry:
        """Convert a SQLite Row to a JournalEntry."""
        return JournalEntry(
            journal_id=row["journal_id"],
            db_path=row["db_path"],
            operation=row["operation"],
            query=row["query"],
            params=json.loads(row["params"]) if row["params"] else [],
            before_data=row["before_data"] or "[]",
            after_data=row["after_data"] or "[]",
            affected_rows=row["affected_rows"] or 0,
            lastrowid=row["lastrowid"],
            tenant_id=row["tenant_id"],
            created_at=row["created_at"],
            rolled_back=bool(row["rolled_back"]),
        )
