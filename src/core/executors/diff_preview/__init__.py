"""
ZENIC-AGENTS - Diff Preview Engine (C1: Simulation Engine)

Shows before/after diffs of what changes would occur if an action
were executed.  For each action type the engine inspects the current
state and computes the delta:

* **DB**   – uses DBTransactionJournal to get current snapshots,
  then computes what would change.
* **File** – compares current file state with proposed changes.
* **Email** – shows the email that would be sent (from, to, subject).

Thread-safe: All public methods guarded by RLock.
Retry logic: DB reads wrapped with 3 retries, exponential backoff.
Singleton: get_diff_preview_engine() / reset_diff_preview_engine().
"""

from ._comparator import (
    build_db_summary,
    count_placeholders_in_set,
    estimate_risk_from_diffs,
    extract_where_clause,
    parse_insert_columns,
    parse_set_fields,
    retry,
)
from ._formatter import format_diff, truncate
from ._generator import (
    DiffPreviewEngine,
    get_diff_preview_engine,
    reset_diff_preview_engine,
)
from ._types import DiffEntry, DiffResult

__all__ = [
    "DiffEntry",
    "DiffResult",
    "DiffPreviewEngine",
    "get_diff_preview_engine",
    "reset_diff_preview_engine",
]
