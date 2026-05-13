"""
ZENIC-AGENTS - DB Transaction Journal (A3 Rollback Enhancement)

Snapshots data BEFORE every write operation so that it can be restored
exactly on rollback.  Works as an undo-log for SQLite databases.

Features:
  - Captures row state before DELETE / UPDATE via an automatic SELECT
  - Records that no prior data existed for INSERT operations
  - Rollback restores the exact captured state:
      DELETE -> re-inserts captured rows
      UPDATE -> restores old column values
      INSERT -> deletes the row by lastrowid
  - SQLite persistence (db_journal.sqlite) for crash recovery
  - Thread-safe via RLock
  - Every DB operation wrapped in retry (3 retries, 0.5s base delay)
  - Singleton pattern with get_db_journal() / reset_db_journal()
  - Proper __all__ exports
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.shared.retry import with_retry
from src.core.shared.db_initializer import get_data_dir

logger = logging.getLogger(__name__)

__all__ = [
    "JournalEntry",
    "RollbackResult",
    "DBTransactionJournal",
    "get_db_journal",
    "reset_db_journal",
]

# ──────────────────────────────────────────────────────────────
#  DATA MODELS
# ──────────────────────────────────────────────────────────────


@dataclass
class JournalEntry:
    """A single journal record capturing state before a write operation.

    Attributes:
        journal_id: Unique identifier for this journal entry.
        db_path: Path to the SQLite database that was modified.
        operation: The SQL operation type (INSERT, UPDATE, DELETE).
        query: The SQL query that was (or will be) executed.
        params: The query parameters.
        before_data: JSON string of row state BEFORE the write.
            For DELETE/UPDATE this is a list of dicts captured via SELECT.
            For INSERT this is ``"[]"`` (no prior data existed).
        after_data: JSON string of row state AFTER the write (populated by
            ``journal_after``).  ``"[]"`` until ``journal_after`` is called.
        affected_rows: Number of rows affected by the write.
        lastrowid: The ``lastrowid`` from the cursor (for INSERT rollback).
        tenant_id: Tenant that owns this journal entry.
        created_at: Unix timestamp when the journal entry was created.
        rolled_back: Whether this entry has already been rolled back.
    """

    journal_id: str = ""
    db_path: str = ""
    operation: str = ""
    query: str = ""
    params: List[Any] = field(default_factory=list)
    before_data: str = "[]"
    after_data: str = "[]"
    affected_rows: int = 0
    lastrowid: Optional[int] = None
    tenant_id: str = ""
    created_at: float = 0.0
    rolled_back: bool = False

    def __post_init__(self) -> None:
        if not self.journal_id:
            self.journal_id = uuid.uuid4().hex
        if not self.created_at:
            self.created_at = time.time()


@dataclass
class RollbackResult:
    """Result of a rollback operation.

    Attributes:
        success: Whether the rollback completed without errors.
        journal_id: The journal entry that was rolled back.
        operation: The original operation type that was reversed.
        rows_restored: Number of rows restored by the rollback.
        errors: List of error messages encountered during rollback.
    """

    success: bool = False
    journal_id: str = ""
    operation: str = ""
    rows_restored: int = 0
    errors: List[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────
#  SQL HELPERS
# ──────────────────────────────────────────────────────────────

# Matches common SQL DML keywords at the start of a statement
_OP_PATTERN = re.compile(r"^\s*(INSERT|UPDATE|DELETE)", re.IGNORECASE)


def _classify_operation(query: str) -> str:
    """Return the SQL operation keyword (upper-cased) or empty string."""
    m = _OP_PATTERN.match(query)
    return m.group(1).upper() if m else ""


def _extract_table_from_insert(query: str) -> str:
    """Best-effort extraction of the table name from an INSERT statement."""
    m = re.match(
        r"^\s*INSERT\s+(?:INTO\s+)?[\"']?(\w+)[\"']?",
        query,
        re.IGNORECASE,
    )
    return m.group(1) if m else ""


def _extract_table_and_where_from_update(query: str) -> tuple[str, str]:
    """Best-effort extraction of table name and WHERE clause from UPDATE."""
    m = re.match(
        r"^\s*UPDATE\s+[\"']?(\w+)[\"']?\s+SET\s+.+?\s+WHERE\s+(.+)$",
        query,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1), m.group(2)
    # No WHERE clause — update targets all rows
    m2 = re.match(
        r"^\s*UPDATE\s+[\"']?(\w+)[\"']?\s+SET\s+",
        query,
        re.IGNORECASE,
    )
    return (m2.group(1), "") if m2 else ("", "")


def _extract_set_clause_from_update(query: str) -> str:
    """Best-effort extraction of the SET clause from an UPDATE statement.

    Returns the SET assignments portion (between SET and WHERE), or the
    entire SET portion if no WHERE clause exists.
    """
    m = re.match(
        r"^\s*UPDATE\s+[\"']?(\w+)[\"']?\s+SET\s+(.+?)(?:\s+WHERE\s+.+)?$",
        query,
        re.IGNORECASE | re.DOTALL,
    )
    return m.group(2).strip() if m else ""


def _count_placeholders(clause: str) -> int:
    """Count the number of ``?`` placeholders in a SQL fragment."""
    return clause.count("?")


def _extract_table_and_where_from_delete(query: str) -> tuple[str, str]:
    """Best-effort extraction of table name and WHERE clause from DELETE."""
    m = re.match(
        r"^\s*DELETE\s+FROM\s+[\"']?(\w+)[\"']?\s+WHERE\s+(.+)$",
        query,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1), m.group(2)
    # No WHERE clause
    m2 = re.match(
        r"^\s*DELETE\s+FROM\s+[\"']?(\w+)[\"']?",
        query,
        re.IGNORECASE,
    )
    return (m2.group(1), "") if m2 else ("", "")


# ──────────────────────────────────────────────────────────────
#  DB TRANSACTION JOURNAL
# ──────────────────────────────────────────────────────────────


class DBTransactionJournal:
    """Captures row state before every write operation so that it can be
    restored on rollback.

    Thread-safe.  Persists journal entries to SQLite so they survive
    process restarts.  Every DB operation is wrapped in retry logic.
    """

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
                conn.execute(
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
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_je_db_tenant "
                    "ON journal_entries(db_path, tenant_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_je_tenant "
                    "ON journal_entries(tenant_id)"
                )
                conn.execute(
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
                conn.execute(
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

    def rollback_to(self, journal_id: str) -> RollbackResult:
        """Restore the exact state captured in the journal entry.

        - DELETE → re-inserts the captured rows.
        - UPDATE → restores old column values.
        - INSERT → deletes the inserted row by ``lastrowid``.

        Args:
            journal_id: The journal entry to roll back.

        Returns:
            A ``RollbackResult`` indicating success / failure.
        """
        with self._lock:
            entry = self.get_journal(journal_id)
            if entry is None:
                return RollbackResult(
                    success=False,
                    journal_id=journal_id,
                    errors=[f"Journal entry {journal_id} not found"],
                )

            if entry.rolled_back:
                return RollbackResult(
                    success=False,
                    journal_id=journal_id,
                    operation=entry.operation,
                    errors=[f"Journal entry {journal_id} already rolled back"],
                )

            result = RollbackResult(
                journal_id=journal_id,
                operation=entry.operation,
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

                # Mark as rolled back
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
        """Retrieve a journal entry by its ID.

        Args:
            journal_id: The unique journal entry identifier.

        Returns:
            The ``JournalEntry`` if found, else ``None``.
        """

        def _do_get() -> Optional[JournalEntry]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(
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
            _do_get,
            max_retries=3,
            base_delay=0.5,
            label=f"db_journal.get_journal({journal_id[:12]})",
        )

    def list_journals(
        self,
        db_path: str,
        tenant_id: str,
        limit: int = 100,
    ) -> List[JournalEntry]:
        """List journal entries for a specific database and tenant.

        Args:
            db_path: The database path to filter by.
            tenant_id: The tenant identifier to filter by.
            limit: Maximum number of entries to return (default 100).

        Returns:
            A list of ``JournalEntry`` objects, newest first.
        """

        def _do_list() -> List[JournalEntry]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(
                    """
                    SELECT * FROM journal_entries
                    WHERE db_path = ? AND tenant_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (db_path, tenant_id, limit),
                )
                return [self._row_to_entry(row) for row in cursor.fetchall()]
            finally:
                conn.close()

        return with_retry(
            _do_list,
            max_retries=3,
            base_delay=0.5,
            label="db_journal.list_journals",
        )

    def prune_journals(self, older_than_hours: int, tenant_id: str) -> int:
        """Delete journal entries older than the specified number of hours.

        Only non-rolled-back entries are pruned (rolled-back entries are
        kept for audit trail).

        Args:
            older_than_hours: Minimum age in hours for entries to prune.
            tenant_id: The tenant whose entries to prune.

        Returns:
            The number of entries deleted.
        """
        cutoff = time.time() - (older_than_hours * 3600)

        def _do_prune() -> int:
            conn = sqlite3.connect(self._db_path)
            try:
                cursor = conn.execute(
                    """
                    DELETE FROM journal_entries
                    WHERE created_at < ?
                      AND tenant_id = ?
                      AND rolled_back = 0
                    """,
                    (cutoff, tenant_id),
                )
                conn.commit()
                deleted = cursor.rowcount
                logger.info(
                    "DBTransactionJournal: prune_journals deleted %d entries "
                    "older than %dh [tenant=%s]",
                    deleted, older_than_hours, tenant_id,
                )
                return deleted
            finally:
                conn.close()

        return with_retry(
            _do_prune,
            max_retries=3,
            base_delay=0.5,
            label="db_journal.prune_journals",
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
                    cursor = conn.execute(select_query, select_params)
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

    # ── Rollback helpers ─────────────────────────────────────

    def _rollback_delete(
        self,
        entry: JournalEntry,
        result: RollbackResult,
    ) -> int:
        """Re-insert rows that were captured before a DELETE."""
        before_data: List[Dict[str, Any]] = json.loads(entry.before_data)
        if not before_data:
            return 0

        restored = 0

        def _do_restore() -> int:
            nonlocal restored
            # For DELETE rollback we need to know the table name
            table, _ = _extract_table_and_where_from_delete(entry.query)
            if not table:
                result.errors.append(
                    "Cannot determine table name for DELETE rollback"
                )
                return restored
            conn = sqlite3.connect(entry.db_path)
            try:
                for row in before_data:
                    if not row:
                        continue
                    columns = list(row.keys())
                    placeholders = ", ".join(["?"] * len(columns))
                    col_names = ", ".join(columns)
                    values = [row[c] for c in columns]
                    insert_sql = (
                        f"INSERT OR REPLACE INTO {table}"
                        f" ({col_names}) VALUES ({placeholders})"
                    )
                    conn.execute(insert_sql, values)
                    restored += 1
                conn.commit()
            except Exception as exc:
                conn.rollback()
                result.errors.append(f"DELETE rollback row failed: {exc}")
            finally:
                conn.close()
            return restored

        return with_retry(
            _do_restore,
            max_retries=3,
            base_delay=0.5,
            label=f"db_journal._rollback_delete({entry.journal_id[:12]})",
        )

    def _rollback_update(
        self,
        entry: JournalEntry,
        result: RollbackResult,
    ) -> int:
        """Restore old column values for rows captured before an UPDATE."""
        before_data: List[Dict[str, Any]] = json.loads(entry.before_data)
        if not before_data:
            return 0

        table, _ = _extract_table_and_where_from_update(entry.query)
        if not table:
            result.errors.append("Cannot determine table name for UPDATE rollback")
            return 0

        restored = 0

        def _do_restore() -> int:
            nonlocal restored
            conn = sqlite3.connect(entry.db_path)
            try:
                for row in before_data:
                    if not row:
                        continue
                    # Build an UPDATE statement that restores every column
                    # to its original value.  We use the first column (typically
                    # the primary key) as the WHERE condition.
                    columns = list(row.keys())
                    if not columns:
                        continue
                    set_clause = ", ".join(f"{col} = ?" for col in columns)
                    values = [row[c] for c in columns]
                    # Use the first column as the identifying column
                    pk_col = columns[0]
                    pk_val = row[pk_col]
                    update_sql = (
                        f"UPDATE {table} SET {set_clause} WHERE {pk_col} = ?"
                    )
                    conn.execute(update_sql, values + [pk_val])
                    restored += 1
                conn.commit()
            except Exception as exc:
                conn.rollback()
                result.errors.append(f"UPDATE rollback row failed: {exc}")
            finally:
                conn.close()
            return restored

        return with_retry(
            _do_restore,
            max_retries=3,
            base_delay=0.5,
            label=f"db_journal._rollback_update({entry.journal_id[:12]})",
        )

    def _rollback_insert(
        self,
        entry: JournalEntry,
        result: RollbackResult,
    ) -> int:
        """Delete the row that was inserted (identified by lastrowid)."""
        if entry.lastrowid is None or entry.lastrowid == 0:
            result.errors.append(
                "Cannot rollback INSERT: lastrowid is not available"
            )
            return 0

        table = _extract_table_from_insert(entry.query)
        if not table:
            result.errors.append(
                "Cannot determine table name for INSERT rollback"
            )
            return 0

        restored = 0

        def _do_restore() -> int:
            nonlocal restored
            conn = sqlite3.connect(entry.db_path)
            try:
                cursor = conn.execute(
                    f"DELETE FROM {table} WHERE rowid = ?",
                    (entry.lastrowid,),
                )
                conn.commit()
                if cursor.rowcount > 0:
                    restored = cursor.rowcount
                else:
                    result.errors.append(
                        f"INSERT rollback: no row found with rowid={entry.lastrowid}"
                    )
            except Exception as exc:
                conn.rollback()
                result.errors.append(f"INSERT rollback failed: {exc}")
            finally:
                conn.close()
            return restored

        return with_retry(
            _do_restore,
            max_retries=3,
            base_delay=0.5,
            label=f"db_journal._rollback_insert({entry.journal_id[:12]})",
        )

    # ── Persistence helpers ──────────────────────────────────

    def _persist_entry(self, entry: JournalEntry) -> None:
        """Write a JournalEntry to SQLite."""

        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(
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
                conn.execute(
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


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

_instance: Optional[DBTransactionJournal] = None
_instance_lock = threading.Lock()


def get_db_journal() -> DBTransactionJournal:
    """Return the singleton DBTransactionJournal instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DBTransactionJournal()
    return _instance


def reset_db_journal() -> None:
    """Reset the singleton instance (mainly for testing)."""
    global _instance
    with _instance_lock:
        _instance = None
