"""
db_journal._helpers — SQL parsing helpers for the DB transaction journal.
"""

from __future__ import annotations

import re


# Matches common SQL DML keywords at the start of a statement
_OP_PATTERN = re.compile(r"^\s*(INSERT|UPDATE|DELETE)", re.IGNORECASE)


def classify_operation(query: str) -> str:
    """Return the SQL operation keyword (upper-cased) or empty string."""
    m = _OP_PATTERN.match(query)
    return m.group(1).upper() if m else ""


def extract_table_from_insert(query: str) -> str:
    """Best-effort extraction of the table name from an INSERT statement."""
    m = re.match(
        r"^\s*INSERT\s+(?:INTO\s+)?[\"']?(\w+)[\"']?",
        query, re.IGNORECASE,
    )
    return m.group(1) if m else ""


def extract_table_and_where_from_update(query: str) -> tuple[str, str]:
    """Best-effort extraction of table name and WHERE clause from UPDATE."""
    m = re.match(
        r"^\s*UPDATE\s+[\"']?(\w+)[\"']?\s+SET\s+.+?\s+WHERE\s+(.+)$",
        query, re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1), m.group(2)
    m2 = re.match(
        r"^\s*UPDATE\s+[\"']?(\w+)[\"']?\s+SET\s+",
        query, re.IGNORECASE,
    )
    return (m2.group(1), "") if m2 else ("", "")


def extract_set_clause_from_update(query: str) -> str:
    """Best-effort extraction of the SET clause from an UPDATE statement."""
    m = re.match(
        r"^\s*UPDATE\s+[\"']?(\w+)[\"']?\s+SET\s+(.+?)(?:\s+WHERE\s+.+)?$",
        query, re.IGNORECASE | re.DOTALL,
    )
    return m.group(2).strip() if m else ""


def count_placeholders(clause: str) -> int:
    """Count the number of ``?`` placeholders in a SQL fragment."""
    return clause.count("?")


def extract_table_and_where_from_delete(query: str) -> tuple[str, str]:
    """Best-effort extraction of table name and WHERE clause from DELETE."""
    m = re.match(
        r"^\s*DELETE\s+FROM\s+[\"']?(\w+)[\"']?\s+WHERE\s+(.+)$",
        query, re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1), m.group(2)
    m2 = re.match(
        r"^\s*DELETE\s+FROM\s+[\"']?(\w+)[\"']?",
        query, re.IGNORECASE,
    )
    return (m2.group(1), "") if m2 else ("", "")
