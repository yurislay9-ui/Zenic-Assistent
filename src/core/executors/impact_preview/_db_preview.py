"""ZENIC-AGENTS - Impact Preview Engine: Database Preview Logic

Simulates the effects of database operations WITHOUT executing them.
All operations are strictly READ-ONLY — this module never modifies data.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any, Dict, List, Optional

from ._types import (
    ImpactRiskLevel,
    ImpactField,
    DBImpactPreview,
)
from ._retry import _retry_db_operation
from ._sql_parsing import (
    extract_table_name,
    extract_where_clause,
    extract_set_fields,
    extract_insert_columns,
    count_set_placeholders,
)

logger = logging.getLogger(__name__)


def preview_db_operation(
    config: Dict[str, Any],
    db_retry_max: int = 3,
    db_retry_base_delay: float = 0.5,
) -> DBImpactPreview:
    """Preview a database operation WITHOUT executing it.

    For DELETE: counts matching rows using SELECT COUNT(*) with same WHERE.
    For UPDATE: shows before->after diff of field values.
    For INSERT: validates constraints (NOT NULL, UNIQUE, etc.).
    For SELECT: reports row count estimate.

    All operations are strictly READ-ONLY.

    Args:
        config: DB operation config with keys like db_path, operation, query, params.
        db_retry_max: Maximum retry attempts for DB operations.
        db_retry_base_delay: Base delay in seconds for exponential backoff.

    Returns:
        A DBImpactPreview with the estimated impact.
    """
    db_path = config.get("db_path", ":memory:")
    operation = str(config.get("operation", "query")).upper()
    query = str(config.get("query", ""))
    params = config.get("params", [])
    table = extract_table_name(query, operation)

    if not isinstance(params, (list, tuple)):
        params = [params]

    # Base preview
    preview = DBImpactPreview(
        operation=operation,
        table=table,
        risk_level=ImpactRiskLevel.NONE,
        risk_score=0.0,
        summary=f"DB {operation} on table '{table}'",
        reversible=True,
    )

    # Try to connect and inspect
    try:
        if operation in ("DELETE",):
            preview = _preview_delete(db_path, query, params, table, preview, db_retry_max, db_retry_base_delay)
        elif operation in ("UPDATE",):
            preview = _preview_update(db_path, query, params, table, preview, db_retry_max, db_retry_base_delay)
        elif operation in ("INSERT",):
            preview = _preview_insert(db_path, query, params, table, preview, db_retry_max, db_retry_base_delay)
        elif operation in ("QUERY", "SELECT"):
            preview = _preview_select(db_path, query, params, table, preview, db_retry_max, db_retry_base_delay)
        else:
            preview.summary = f"Unknown DB operation: {operation}"
            preview.warnings.append(f"Cannot preview unknown operation: {operation}")
    except Exception as exc:
        logger.warning(
            "ImpactPreviewEngine: DB preview failed for %s on %s: %s",
            operation, table, exc,
        )
        preview.summary = f"Could not preview DB {operation}: {exc}"
        preview.warnings.append(f"Preview error: {exc}")
        preview.risk_level = ImpactRiskLevel.MEDIUM
        preview.risk_score = 0.4

    return preview


def _preview_delete(
    db_path: str,
    query: str,
    params: List[Any],
    table: str,
    preview: DBImpactPreview,
    db_retry_max: int,
    db_retry_base_delay: float,
) -> DBImpactPreview:
    """Preview a DELETE operation: count matching rows using SELECT COUNT(*)."""
    if not table:
        preview.summary = "DELETE without identifiable table"
        preview.risk_level = ImpactRiskLevel.HIGH
        preview.risk_score = 0.9
        preview.warnings.append("Cannot determine target table for DELETE")
        return preview

    # Build COUNT query with same WHERE clause
    where_clause = extract_where_clause(query)
    count_query = f"SELECT COUNT(*) FROM {table}"
    if where_clause:
        count_query += f" WHERE {where_clause}"

    def _count_rows() -> int:
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(count_query, params)  # nosemgrep: sqlalchemy-execute-raw-query
            row = cursor.fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()

    try:
        count = _retry_db_operation(
            _count_rows,
            max_retries=db_retry_max,
            base_delay=db_retry_base_delay,
        )
        preview.estimated_rows = count
        preview.affected_rows = count
        preview.reversible = False
        preview.summary = f"DELETE from {table}: {count} row(s) would be removed"

        if count == 0:
            preview.risk_level = ImpactRiskLevel.LOW
            preview.risk_score = 0.1
            preview.summary = f"DELETE from {table}: no rows match the WHERE clause"
        elif count > 100:
            preview.risk_level = ImpactRiskLevel.CRITICAL
            preview.risk_score = 1.0
            preview.warnings.append(f"Bulk DELETE: {count} rows would be removed")
        elif count > 10:
            preview.risk_level = ImpactRiskLevel.HIGH
            preview.risk_score = 0.8
            preview.warnings.append(f"Multiple rows affected: {count}")
        else:
            preview.risk_level = ImpactRiskLevel.MEDIUM
            preview.risk_score = 0.5

        # Check if there's no WHERE clause (delete all)
        if not where_clause:
            preview.risk_level = ImpactRiskLevel.CRITICAL
            preview.risk_score = 1.0
            preview.warnings.append("DELETE without WHERE clause — ALL rows would be removed")
            preview.summary = f"DELETE ALL from {table}: {count} row(s) would be removed"

    except Exception as exc:
        preview.summary = f"Could not estimate DELETE impact: {exc}"
        preview.risk_level = ImpactRiskLevel.HIGH
        preview.risk_score = 0.7
        preview.warnings.append(f"Row count estimation failed: {exc}")

    return preview


def _preview_update(
    db_path: str,
    query: str,
    params: List[Any],
    table: str,
    preview: DBImpactPreview,
    db_retry_max: int,
    db_retry_base_delay: float,
) -> DBImpactPreview:
    """Preview an UPDATE operation: show before->after diff of field values."""
    if not table:
        preview.summary = "UPDATE without identifiable table"
        preview.risk_level = ImpactRiskLevel.HIGH
        preview.risk_score = 0.9
        preview.warnings.append("Cannot determine target table for UPDATE")
        return preview

    # Extract SET clause fields
    set_fields = extract_set_fields(query)
    where_clause = extract_where_clause(query)

    # Count placeholders (?) in the SET clause to correctly slice params.
    # In "UPDATE t SET a = ?, b = ? WHERE c = ?", the first 2 params
    # belong to SET and the rest belong to WHERE.
    set_placeholders = count_set_placeholders(query)
    where_params = list(params[set_placeholders:]) if set_placeholders < len(params) else []

    # Count affected rows
    count_query = f"SELECT COUNT(*) FROM {table}"
    if where_clause:
        count_query += f" WHERE {where_clause}"

    def _count_rows() -> int:
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(count_query, where_params)  # nosemgrep: sqlalchemy-execute-raw-query
            row = cursor.fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()

    try:
        count = _retry_db_operation(
            _count_rows,
            max_retries=db_retry_max,
            base_delay=db_retry_base_delay,
        )
        preview.estimated_rows = count
        preview.affected_rows = count

        # Fetch a sample row to show current values
        if count > 0:
            sample_query = f"SELECT * FROM {table}"
            if where_clause:
                sample_query += f" WHERE {where_clause}"
            sample_query += " LIMIT 1"

            def _fetch_sample() -> Optional[Dict[str, Any]]:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                try:
                    cursor = conn.execute(sample_query, where_params)  # nosemgrep: sqlalchemy-execute-raw-query
                    row = cursor.fetchone()
                    return dict(row) if row else None
                finally:
                    conn.close()

            sample = _retry_db_operation(
                _fetch_sample,
                max_retries=db_retry_max,
                base_delay=db_retry_base_delay,
            )

            # Build field diffs
            for field_name, proposed_value in set_fields:
                current_value = None
                changed = True
                if sample and field_name in sample:
                    current_value = sample[field_name]
                    changed = (current_value != proposed_value)
                preview.fields.append(ImpactField(
                    name=field_name,
                    current_value=current_value,
                    proposed_value=proposed_value,
                    field_type=type(proposed_value).__name__ if proposed_value is not None else "unknown",
                    changed=changed,
                ))

        # Risk assessment
        preview.reversible = False
        field_names = [f.name for f in preview.fields]
        preview.summary = (
            f"UPDATE {table}: {count} row(s), fields: {', '.join(field_names) if field_names else 'unknown'}"
        )

        if not where_clause:
            preview.risk_level = ImpactRiskLevel.CRITICAL
            preview.risk_score = 1.0
            preview.warnings.append("UPDATE without WHERE clause — ALL rows would be affected")
        elif count > 100:
            preview.risk_level = ImpactRiskLevel.HIGH
            preview.risk_score = 0.8
            preview.warnings.append(f"Bulk UPDATE: {count} rows affected")
        elif count > 10:
            preview.risk_level = ImpactRiskLevel.MEDIUM
            preview.risk_score = 0.5
        else:
            preview.risk_level = ImpactRiskLevel.LOW
            preview.risk_score = 0.3

    except Exception as exc:
        preview.summary = f"Could not estimate UPDATE impact: {exc}"
        preview.risk_level = ImpactRiskLevel.HIGH
        preview.risk_score = 0.7
        preview.warnings.append(f"Impact estimation failed: {exc}")

    return preview


def _preview_insert(
    db_path: str,
    query: str,
    params: List[Any],
    table: str,
    preview: DBImpactPreview,
    db_retry_max: int,
    db_retry_base_delay: float,
) -> DBImpactPreview:
    """Preview an INSERT operation: validate constraints."""
    if not table:
        preview.summary = "INSERT without identifiable table"
        preview.risk_level = ImpactRiskLevel.HIGH
        preview.risk_score = 0.9
        preview.warnings.append("Cannot determine target table for INSERT")
        return preview

    # Inspect table schema to validate constraints
    # SECURITY: Validate table/index names before interpolation into PRAGMA
    _safe_id_re = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
    if not _safe_id_re.match(table):
        preview.warnings.append(f"Invalid table name: {table!r}")
        preview.constraints_valid = False
        return preview

    def _inspect_schema() -> List[Dict[str, Any]]:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(f'PRAGMA table_info("{table}")')  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    try:
        columns = _retry_db_operation(
            _inspect_schema,
            max_retries=db_retry_max,
            base_delay=db_retry_base_delay,
        )

        if not columns:
            preview.warnings.append(f"Table '{table}' not found or has no columns")
            preview.constraints_valid = False
            preview.constraint_violations.append(f"Table '{table}' does not exist")
            preview.risk_level = ImpactRiskLevel.HIGH
            preview.risk_score = 0.8
            preview.summary = f"INSERT into {table}: table does not exist"
            return preview

        # Check NOT NULL constraints
        for col in columns:
            col_name = col.get("name", "")
            notnull = col.get("notnull", 0)
            if notnull:
                # Check if a corresponding param exists
                col_idx = None
                # Try to find column index from query
                insert_cols = extract_insert_columns(query)
                if insert_cols:
                    try:
                        col_idx = insert_cols.index(col_name)
                    except ValueError:
                        pass

                if col_idx is not None and col_idx < len(params):
                    if params[col_idx] is None:
                        preview.constraints_valid = False
                        preview.constraint_violations.append(
                            f"NOT NULL violation: column '{col_name}' cannot be NULL"
                        )
                elif col_idx is None and not query.upper().startswith("INSERT INTO"):
                    # Fallback: if we can't parse, warn
                    pass

        # Check UNIQUE constraints
        def _get_unique_constraints() -> List[List[str]]:
            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.execute(f'PRAGMA index_list("{table}")')  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier
                indexes = cursor.fetchall()
                unique_constraints: List[List[str]] = []
                for idx_row in indexes:
                    if idx_row[2]:  # unique flag
                        idx_name = idx_row[1]
                        # SECURITY: Validate index name from DB before interpolation
                        if not _safe_id_re.match(str(idx_name)):
                            continue
                        col_cursor = conn.execute(f'PRAGMA index_info("{idx_name}")')  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier
                        cols = [row[2] for row in col_cursor.fetchall()]
                        unique_constraints.append(cols)
                return unique_constraints
            finally:
                conn.close()

        unique_groups = _retry_db_operation(
            _get_unique_constraints,
            max_retries=db_retry_max,
            base_delay=db_retry_base_delay,
        )

        for unique_cols in unique_groups:
            insert_cols = extract_insert_columns(query)
            if insert_cols:
                matching_indices = []
                all_present = True
                for uc in unique_cols:
                    try:
                        matching_indices.append(insert_cols.index(uc))
                    except ValueError:
                        all_present = False
                        break

                if all_present and matching_indices:
                    # Check for existing rows with same unique values
                    where_parts = [f"{unique_cols[i]} = ?" for i in range(len(unique_cols))]
                    check_query = f"SELECT COUNT(*) FROM {table} WHERE {' AND '.join(where_parts)}"
                    check_params = [params[i] for i in matching_indices if i < len(params)]

                    def _check_unique() -> int:
                        conn = sqlite3.connect(db_path)
                        try:
                            cursor = conn.execute(check_query, check_params)  # nosemgrep: sqlalchemy-execute-raw-query
                            row = cursor.fetchone()
                            return int(row[0]) if row else 0
                        finally:
                            conn.close()

                    existing = _retry_db_operation(
                        _check_unique,
                        max_retries=db_retry_max,
                        base_delay=db_retry_base_delay,
                    )
                    if existing > 0:
                        preview.constraints_valid = False
                        preview.constraint_violations.append(
                            f"UNIQUE violation: ({', '.join(unique_cols)}) already exists"
                        )

        preview.affected_rows = 1
        preview.estimated_rows = 1
        preview.reversible = True  # DELETE can undo INSERT
        insert_cols = extract_insert_columns(query)
        preview.summary = (
            f"INSERT into {table}: 1 row, columns: {', '.join(insert_cols) if insert_cols else 'unknown'}"
        )

        if preview.constraints_valid:
            preview.risk_level = ImpactRiskLevel.LOW
            preview.risk_score = 0.2
        else:
            preview.risk_level = ImpactRiskLevel.MEDIUM
            preview.risk_score = 0.5
            preview.summary += " (constraint violations detected)"

    except Exception as exc:
        preview.summary = f"Could not estimate INSERT impact: {exc}"
        preview.risk_level = ImpactRiskLevel.HIGH
        preview.risk_score = 0.7
        preview.warnings.append(f"Constraint check failed: {exc}")

    return preview


def _preview_select(
    db_path: str,
    query: str,
    params: List[Any],
    table: str,
    preview: DBImpactPreview,
    db_retry_max: int,
    db_retry_base_delay: float,
) -> DBImpactPreview:
    """Preview a SELECT/QUERY operation: report row count estimate."""
    # SELECT is read-only, low risk
    preview.reversible = True
    preview.read_only = True

    # Try to estimate row count
    if table:
        count_query = f"SELECT COUNT(*) FROM {table}"
        where_clause = extract_where_clause(query)
        if where_clause:
            count_query += f" WHERE {where_clause}"

        def _count_rows() -> int:
            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.execute(count_query, params)  # nosemgrep: sqlalchemy-execute-raw-query
                row = cursor.fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()

        try:
            count = _retry_db_operation(
                _count_rows,
                max_retries=db_retry_max,
                base_delay=db_retry_base_delay,
            )
            preview.estimated_rows = count
            preview.summary = f"SELECT from {table}: ~{count} row(s) would be returned"
        except Exception as exc:
            preview.summary = f"SELECT from {table}: could not estimate row count"
            preview.warnings.append(f"Row count estimation failed: {exc}")
    else:
        preview.summary = "SELECT query: read-only operation"

    preview.risk_level = ImpactRiskLevel.NONE
    preview.risk_score = 0.0
    return preview
