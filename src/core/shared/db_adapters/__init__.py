"""
ZENIC-AGENTS v16 - Database Adapter Layer

Phase 3: Provides a unified database interface that abstracts over
SQLite (development/Termux) and PostgreSQL (production/VPS).

Strategy:
  - ZENIC_ENV=development → SQLite (default, backward compatible)
  - ZENIC_ENV=production  → PostgreSQL (via asyncpg / psycopg2)

All modules should use `get_db()` to obtain the correct adapter,
which provides a consistent API regardless of the backend.

Usage:
    from src.core.shared.db_adapters import get_db, DatabaseBackend

    db = get_db()
    async with db.connection() as conn:
        rows = await db.fetch_all(conn, "SELECT * FROM users WHERE tenant_id = $1", [tenant_id])
"""

import logging
import os
from typing import Optional

from ._base import DatabaseBackend
from ._sqlite import SQLiteDatabase
from ._postgresql import PostgreSQLDatabase

logger = logging.getLogger(__name__)

__all__ = [
    "DatabaseBackend",
    "SQLiteDatabase",
    "PostgreSQLDatabase",
    "get_db",
    "get_db_backend",
    "is_postgresql",
]


# ── Singleton instance ────────────────────────────────────
_db_instance: Optional[DatabaseBackend] = None


def is_postgresql() -> bool:
    """Check if the configured database backend is PostgreSQL."""
    return os.environ.get("ZENIC_ENV") == "production" or bool(os.environ.get("DATABASE_URL", "").startswith("postgresql"))


def get_db_backend() -> str:
    """Return the active database backend name."""
    return "postgresql" if is_postgresql() else "sqlite"


def get_db() -> DatabaseBackend:
    """Get or create the singleton database adapter.

    Uses environment variables to determine the backend:
    - ZENIC_ENV=production or DATABASE_URL starts with 'postgresql' → PostgreSQLDatabase
    - Otherwise → SQLiteDatabase (default, backward compatible)
    """
    global _db_instance
    if _db_instance is not None:
        return _db_instance

    if is_postgresql():
        dsn = os.environ.get("DATABASE_URL", "")
        _db_instance = PostgreSQLDatabase(dsn=dsn)
        logger.info("Database backend: PostgreSQL (production)")
    else:
        _db_instance = SQLiteDatabase()
        logger.info("Database backend: SQLite (development)")

    return _db_instance


def reset_db() -> None:
    """Reset the singleton — mainly for testing."""
    global _db_instance
    _db_instance = None
