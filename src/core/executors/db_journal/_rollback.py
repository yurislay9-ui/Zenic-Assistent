"""
ZENIC-AGENTS - DB Journal Rollback Mixin

Rollback methods for the DB Transaction Journal.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List

from src.core.shared.retry import with_retry

from ._types import JournalEntry, RollbackResult
from ._sql_helpers import (
    _extract_table_and_where_from_delete,
    _extract_table_and_where_from_update,
    _extract_table_from_insert,
)

logger = logging.getLogger(__name__)


class _RollbackMixin:
    """Rollback methods for DBTransactionJournal."""

    def rollback_to(self, journal_id: str) -> RollbackResult:
        """Restore the exact state captured in the journal entry.

        - DELETE -> re-inserts the captured rows.
        - UPDATE -> restores old column values.
        - INSERT -> deletes the inserted row by ``lastrowid``.

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
                    conn.execute(insert_sql, values)  # nosemgrep: sqlalchemy-execute-raw-query
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
                    conn.execute(update_sql, values + [pk_val])  # nosemgrep: sqlalchemy-execute-raw-query
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
                cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
