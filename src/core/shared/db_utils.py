"""
ZENIC-AGENTS — Shared Database Utility Functions.

Eliminates duplicated SQL utility code across engine modules:
- SQL LIKE injection escaping (duplicated in MacroRouter and GraphAST)
- Tenant data purge operations (duplicated in 3 engines)
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_SAFE_TABLE_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def escape_sql_like(value: str) -> str:
    """Escape SQL LIKE wildcards and backslash to prevent injection.

    Security: Escapes backslash first, then percent and underscore.
    This order is critical — if backslash is not escaped first, a
    backslash in the input could neutralize the % and _ escaping.

    Args:
        value: The raw string to use in a LIKE pattern.

    Returns:
        Escaped string safe for use in LIKE ... ESCAPE '\\' queries.

    Example:
        >>> escape_sql_like("test%file_name")
        'test\\\\%file\\_name'
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def purge_tenant_rows(conn, table: str, tenant_id: str) -> int:
    """Delete all rows for a specific tenant from a table.

    Used for GDPR compliance (right to be forgotten) or
    tenant deprovisioning. This operation is tenant-scoped
    and cannot affect other tenants' data.

    Args:
        conn: SQLite database connection (from db_initializer pool).
        table: Name of the table to purge from.
        tenant_id: Tenant identifier to delete rows for.

    Returns:
        Number of rows deleted, or 0 on error.
    """
    if not _SAFE_TABLE_RE.match(table):
        logger.error("Invalid table name rejected: %s", table)
        return 0
    try:
        # SECURITY: table name validated by _SAFE_TABLE_RE regex above;
        # tenant_id uses ? parameterization to prevent injection
        cursor = conn.execute(f"DELETE FROM {table} WHERE tenant_id=?", (tenant_id,))  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier
        conn.commit()
        count = cursor.rowcount
        if count > 0:
            logger.info("Purged %d rows from %s for tenant '%s'", count, table, tenant_id)
        return count
    except Exception as e:
        logger.error("Purge failed for tenant '%s' from %s: %s", tenant_id, table, e)
        return 0
