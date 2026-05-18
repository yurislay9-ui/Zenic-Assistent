"""
ZENIC-AGENTS - DB Journal Reader Mixin

Read / query methods for the DB Transaction Journal.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from src.core.shared.retry import with_retry

from ._types import JournalEntry
from ._sql_helpers import (
    _extract_table_and_where_from_delete,
    _extract_table_and_where_from_update,
    _extract_set_clause_from_update,
    _count_placeholders,
)

logger = logging.getLogger(__name__)


class _ReaderMixin:
    """Read and query methods for DBTransactionJournal."""

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
                cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
                cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
                cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
