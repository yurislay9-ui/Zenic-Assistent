"""ZENIC-AGENTS - Impact Preview Engine: SQL Parsing Helpers

Pure functions for extracting structural elements from SQL queries.
These are stateless and side-effect free, making them easy to test.
"""

from __future__ import annotations

import re
from typing import List


def extract_table_name(query: str, operation: str) -> str:
    """Extract the table name from a SQL query.

    Handles:
      - DELETE FROM table ...
      - UPDATE table SET ...
      - INSERT INTO table ...
      - SELECT ... FROM table ...
    """
    query_upper = query.upper().strip()

    if operation in ("DELETE",):
        match = re.search(r'\bFROM\s+(\w+)', query_upper)
        return match.group(1).lower() if match else ""

    if operation in ("UPDATE",):
        match = re.search(r'\bUPDATE\s+(\w+)', query_upper)
        return match.group(1).lower() if match else ""

    if operation in ("INSERT",):
        match = re.search(r'\bINTO\s+(\w+)', query_upper)
        return match.group(1).lower() if match else ""

    if operation in ("QUERY", "SELECT"):
        match = re.search(r'\bFROM\s+(\w+)', query_upper)
        return match.group(1).lower() if match else ""

    return ""


def extract_where_clause(query: str) -> str:
    """Extract the WHERE clause from a SQL query (without the WHERE keyword)."""
    match = re.search(
        r'\bWHERE\s+(.*?)(?:\s*;\s*$|\s*$|\s+GROUP\s+|\s+ORDER\s+|\s+LIMIT\s+)',
        query,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    # Fallback: everything after WHERE to end
    match = re.search(r'\bWHERE\s+(.*)', query, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip().rstrip(";").strip() if match else ""


def extract_set_fields(query: str) -> List[tuple]:
    """Extract field=value pairs from UPDATE SET clause.

    Returns list of (field_name, value) tuples.
    Note: values from the query string are symbolic; actual values come from params.
    """
    match = re.search(r'\bSET\s+(.*?)\s+WHERE\b', query, re.IGNORECASE | re.DOTALL)
    if not match:
        # No WHERE clause — SET to end
        match = re.search(r'\bSET\s+(.*)', query, re.IGNORECASE | re.DOTALL)

    if not match:
        return []

    set_clause = match.group(1).strip().rstrip(";")
    fields: List[tuple] = []

    for assignment in set_clause.split(","):
        assignment = assignment.strip()
        eq_match = re.match(r'(\w+)\s*=\s*(.+)', assignment)
        if eq_match:
            field_name = eq_match.group(1)
            value_str = eq_match.group(2).strip()
            # If value is a placeholder (?), mark it as parameterized
            if value_str == "?":
                fields.append((field_name, "<parameterized>"))
            else:
                # Try to parse as a value
                try:
                    if value_str.startswith("'") and value_str.endswith("'"):
                        fields.append((field_name, value_str[1:-1]))
                    elif value_str.upper() == "NULL":
                        fields.append((field_name, None))
                    else:
                        fields.append((field_name, value_str))
                except Exception:
                    fields.append((field_name, value_str))

    return fields


def extract_insert_columns(query: str) -> List[str]:
    """Extract column names from an INSERT INTO table (col1, col2, ...) statement."""
    match = re.search(
        r'\bINTO\s+\w+\s*\(([^)]+)\)',
        query,
        re.IGNORECASE,
    )
    if not match:
        return []
    cols_str = match.group(1)
    return [c.strip() for c in cols_str.split(",")]


def count_set_placeholders(query: str) -> int:
    """Count the number of '?' placeholders in the SET clause of an UPDATE.

    This allows proper slicing of the params list so that only the
    WHERE-related params are passed to the COUNT / sample queries.

    Example:
      "UPDATE t SET a = ?, b = ? WHERE c = ?"  ->  2
      "UPDATE t SET a = 5 WHERE c = ?"          ->  0
    """
    # Extract the SET clause (between SET and WHERE, or SET to end)
    match = re.search(r'\bSET\s+(.*?)\s+WHERE\b', query, re.IGNORECASE | re.DOTALL)
    if not match:
        match = re.search(r'\bSET\s+(.*)', query, re.IGNORECASE | re.DOTALL)
    if not match:
        return 0
    set_clause = match.group(1)
    return set_clause.count('?')
