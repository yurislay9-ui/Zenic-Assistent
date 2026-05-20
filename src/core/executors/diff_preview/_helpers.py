"""
diff_preview._helpers — Retry helper, SQL parsing, risk estimation, and formatting.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, List, Optional

from src.core.executors.diff_preview._types import DiffEntry

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  RETRY HELPER
# ──────────────────────────────────────────────────────────────

def retry(
    fn: Any,
    max_retries: int = 3,
    base_delay: float = 0.1,
    label: str = "diff_preview",
) -> Any:
    """Execute *fn* with exponential-backoff retry.

    Delays: base_delay * 2^attempt  →  0.1s, 0.2s, 0.4s.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.debug(
                    "%s: retry %d/%d after %.2fs — %s",
                    label, attempt + 1, max_retries, delay, exc,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "%s: failed after %d attempts — %s",
                    label, max_retries, exc,
                )
    raise last_exc  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────
#  RISK ESTIMATION
# ──────────────────────────────────────────────────────────────

def estimate_risk_from_diffs(
    diffs: List[DiffEntry],
    operation: str = "",
) -> str:
    """Estimate risk from a list of DiffEntry objects."""
    removed_count = sum(1 for d in diffs if d.change_type == "removed")
    modified_count = sum(1 for d in diffs if d.change_type == "modified")
    total_count = len(diffs)

    if removed_count >= 5 or total_count >= 10:
        return "high"

    op_upper = operation.upper() if isinstance(operation, str) else ""
    if op_upper == "DELETE" and removed_count > 0:
        return "high"

    if removed_count >= 2 or total_count >= 5 or modified_count >= 3:
        return "medium"

    return "low"


# ──────────────────────────────────────────────────────────────
#  SQL PARSING HELPERS
# ──────────────────────────────────────────────────────────────

def extract_where_clause(query: str, operation: str) -> str:
    """Best-effort extraction of WHERE clause from a SQL query."""
    op_upper = operation.upper()

    if op_upper == "DELETE":
        m = re.match(
            r"^\s*DELETE\s+FROM\s+\w+\s+WHERE\s+(.+)$",
            query, re.IGNORECASE | re.DOTALL,
        )
        return m.group(1).strip() if m else ""

    if op_upper == "UPDATE":
        m = re.match(
            r"^\s*UPDATE\s+\w+\s+SET\s+.+?\s+WHERE\s+(.+)$",
            query, re.IGNORECASE | re.DOTALL,
        )
        return m.group(1).strip() if m else ""

    return ""


def parse_set_fields(query: str) -> List[tuple]:
    """Parse SET clause from an UPDATE query.

    Returns:
        List of (field_name, proposed_value) tuples.
    """
    m = re.match(
        r"^\s*UPDATE\s+\w+\s+SET\s+(.+?)(?:\s+WHERE\s+.+)?$",
        query, re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return []

    set_clause = m.group(1).strip()
    fields: List[tuple] = []

    for assignment in set_clause.split(","):
        assignment = assignment.strip()
        eq_match = re.match(r"(\w+)\s*=\s*(.+)", assignment)
        if eq_match:
            field_name = eq_match.group(1)
            value_str = eq_match.group(2).strip()
            if value_str == "?":
                fields.append((field_name, "<placeholder>"))
            elif value_str.startswith("'") and value_str.endswith("'"):
                fields.append((field_name, value_str[1:-1]))
            else:
                try:
                    fields.append((field_name, int(value_str)))
                except ValueError:
                    try:
                        fields.append((field_name, float(value_str)))
                    except ValueError:
                        fields.append((field_name, value_str))

    return fields


def count_placeholders_in_set(query: str) -> int:
    """Count the number of ``?`` placeholders in the SET clause."""
    m = re.match(
        r"^\s*UPDATE\s+\w+\s+SET\s+(.+?)(?:\s+WHERE\s+.+)?$",
        query, re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return 0
    return m.group(1).count("?")


def parse_insert_columns(query: str) -> List[str]:
    """Parse column names from an INSERT query."""
    m = re.match(
        r"^\s*INSERT\s+INTO\s+\w+\s*\(([^)]+)\)",
        query, re.IGNORECASE,
    )
    if not m:
        return []
    cols_str = m.group(1)
    return [c.strip().strip('"').strip("'") for c in cols_str.split(",")]


def build_db_summary(
    operation: str,
    table: str,
    affected_rows: int,
    diffs: List[DiffEntry],
) -> str:
    """Build a human-readable summary for a DB diff."""
    if not diffs:
        return f"DB {operation} on {table}: no changes detected"

    removed = sum(1 for d in diffs if d.change_type == "removed")
    added = sum(1 for d in diffs if d.change_type == "added")
    modified = sum(1 for d in diffs if d.change_type == "modified")

    parts: List[str] = [f"DB {operation} on {table}:"]
    if added:
        parts.append(f"{added} field(s) added")
    if modified:
        parts.append(f"{modified} field(s) modified")
    if removed:
        parts.append(f"{removed} field(s) removed")

    if affected_rows > 0:
        parts.append(f"({affected_rows} row(s) affected)")

    return " ".join(parts)


# ──────────────────────────────────────────────────────────────
#  FORMATTING HELPERS
# ──────────────────────────────────────────────────────────────

def truncate(value: Any, max_len: int = 50) -> str:
    """Truncate a value representation for display."""
    s = str(value)
    if len(s) > max_len:
        return s[:max_len - 3] + "..."
    return s
