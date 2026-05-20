"""
db_journal._mixin_rollback — Rollback helpers mixin for DBTransactionJournal.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import TYPE_CHECKING

from src.core.shared.retry import with_retry
from src.core.executors.db_journal._helpers import (
    extract_table_and_where_from_delete,
    extract_table_and_where_from_update,
    extract_table_from_insert,
)
from src.core.executors.db_journal._types import RollbackResult

if TYPE_CHECKING:
    from src.core.executors.db_journal._types import JournalEntry

logger = logging.getLogger(__name__)


class RollbackMixin:
    """Mixin providing rollback helper methods for DBTransactionJournal."""

    # These attributes are provided by the main class.
    _db_path: str
    _lock: object

    def _rollback_delete(
        self, entry: JournalEntry, result: RollbackResult,
    ) -> int:
        """Re-insert rows that were captured before a DELETE."""
        before_data: list[dict[str, any]] = json.loads(entry.before_data)
        if not before_data:
            return 0

        restored = 0

        def _do_restore() -> int:
            nonlocal restored
            table, _ = extract_table_and_where_from_delete(entry.query)
            if not table:
                result.errors.append("Cannot determine table name for DELETE rollback")
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
                    conn.execute(insert_sql, values)  # nosemgrep
                    restored += 1
                conn.commit()
            except Exception as exc:
                conn.rollback()
                result.errors.append(f"DELETE rollback row failed: {exc}")
            finally:
                conn.close()
            return restored

        return with_retry(
            _do_restore, max_retries=3, base_delay=0.5,
            label=f"db_journal._rollback_delete({entry.journal_id[:12]})",
        )

    def _rollback_update(
        self, entry: JournalEntry, result: RollbackResult,
    ) -> int:
        """Restore old column values for rows captured before an UPDATE."""
        before_data: list[dict[str, any]] = json.loads(entry.before_data)
        if not before_data:
            return 0

        table, _ = extract_table_and_where_from_update(entry.query)
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
                    columns = list(row.keys())
                    if not columns:
                        continue
                    set_clause = ", ".join(f"{col} = ?" for col in columns)
                    values = [row[c] for c in columns]
                    pk_col = columns[0]
                    pk_val = row[pk_col]
                    update_sql = f"UPDATE {table} SET {set_clause} WHERE {pk_col} = ?"
                    conn.execute(update_sql, values + [pk_val])  # nosemgrep
                    restored += 1
                conn.commit()
            except Exception as exc:
                conn.rollback()
                result.errors.append(f"UPDATE rollback row failed: {exc}")
            finally:
                conn.close()
            return restored

        return with_retry(
            _do_restore, max_retries=3, base_delay=0.5,
            label=f"db_journal._rollback_update({entry.journal_id[:12]})",
        )

    def _rollback_insert(
        self, entry: JournalEntry, result: RollbackResult,
    ) -> int:
        """Delete the row that was inserted (identified by lastrowid)."""
        if entry.lastrowid is None or entry.lastrowid == 0:
            result.errors.append("Cannot rollback INSERT: lastrowid is not available")
            return 0

        table = extract_table_from_insert(entry.query)
        if not table:
            result.errors.append("Cannot determine table name for INSERT rollback")
            return 0

        restored = 0

        def _do_restore() -> int:
            nonlocal restored
            conn = sqlite3.connect(entry.db_path)
            try:
                cursor = conn.execute(  # nosemgrep
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
            _do_restore, max_retries=3, base_delay=0.5,
            label=f"db_journal._rollback_insert({entry.journal_id[:12]})",
        )
