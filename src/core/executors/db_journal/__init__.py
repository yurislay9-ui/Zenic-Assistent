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

import logging
import threading
from typing import Optional

# Re-export data models
from ._types import JournalEntry, RollbackResult

# Re-export SQL helpers (used internally but keep accessible)
from ._sql_helpers import (
    _classify_operation,
    _extract_table_from_insert,
    _extract_table_and_where_from_update,
    _extract_set_clause_from_update,
    _count_placeholders,
    _extract_table_and_where_from_delete,
)

# Import mixins
from ._writer import _WriterMixin
from ._reader import _ReaderMixin
from ._rollback import _RollbackMixin

logger = logging.getLogger(__name__)

__all__ = [
    "JournalEntry",
    "RollbackResult",
    "DBTransactionJournal",
    "get_db_journal",
    "reset_db_journal",
]


class DBTransactionJournal(_WriterMixin, _ReaderMixin, _RollbackMixin):
    """Captures row state before every write operation so that it can be
    restored on rollback.

    Thread-safe.  Persists journal entries to SQLite so they survive
    process restarts.  Every DB operation is wrapped in retry logic.
    """

    pass


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
