"""
ZENIC-AGENTS - SQLCipher Adapter (Phase 3)

Encrypted database connection adapter using SQLCipher (AES-256).
Provides transparent encryption at the storage layer with
hardware-binding support for license enforcement.

Falls back to standard SQLite when SQLCipher is not available,
with a warning log indicating the database is unencrypted.

All SQLCipher library resolution is delegated to the shared
sqlcipher_helper module for consistency across the project.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, Tuple

from src.core.shared.sqlcipher_helper import (
    HAS_SQLCIPHER,
    get_sqlcipher_connection,
    is_sqlcipher_available,
    sqlcipher_module,
)

logger = logging.getLogger(__name__)

# Re-export for backward compatibility (db_initializer imports these)
_HAS_SQLCIPHER = HAS_SQLCIPHER


# ──────────────────────────────────────────────────────────────
#  TYPES
# ──────────────────────────────────────────────────────────────

@contextmanager
def _null_context():
    """No-op context manager."""
    yield


# ──────────────────────────────────────────────────────────────
#  SQLCIPHER ADAPTER
# ──────────────────────────────────────────────────────────────

class SQLCipherAdapter:
    """Adapter for SQLCipher encrypted database connections.

    Features:
      - AES-256 encryption at rest via SQLCipher
      - Key derivation from passphrase (PBKDF2-HMAC-SHA256)
      - Graceful fallback to standard SQLite when SQLCipher unavailable
      - Connection pooling with configurable pool size
      - PRAGMA optimization for ARM/mobile
      - Hardware binding (optional, for license enforcement)

    Usage:
        adapter = SQLCipherAdapter(db_path="data.db", passphrase="secret")
        with adapter.connection() as conn:
            conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))  # nosemgrep: sqlalchemy-execute-raw-query
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        passphrase: str = "",
        pool_size: int = 5,
        kdf_iterations: int = 64000,
        cipher_page_size: int = 4096,
        hardware_bind: bool = False,
    ) -> None:
        self._db_path = db_path
        self._passphrase = passphrase
        self._pool_size = pool_size
        self._kdf_iterations = kdf_iterations
        self._cipher_page_size = cipher_page_size
        self._hardware_bind = hardware_bind
        self._encrypted = HAS_SQLCIPHER and bool(passphrase)
        self._pool: List[Any] = []

        if not HAS_SQLCIPHER and passphrase:
            logger.warning(
                "SQLCipherAdapter: SQLCipher not available! "
                "Database '%s' will be UNENCRYPTED. "
                "Install pysqlcipher3 or sqlcipher3-binary for encryption support.",
                db_path,
            )
            self._encrypted = False

    @property
    def is_encrypted(self) -> bool:
        """Whether the database connection uses SQLCipher encryption."""
        return self._encrypted

    @property
    def db_path(self) -> str:
        """The database file path."""
        return self._db_path

    @contextmanager
    def connection(self) -> Generator[Any, None, None]:
        """Get a database connection from the pool.

        Returns an encrypted SQLCipher connection if available,
        otherwise a standard SQLite connection.
        """
        conn = self._get_connection()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            self._return_connection(conn)

    @contextmanager
    def transaction(self) -> Generator[Any, None, None]:
        """Get a connection with automatic transaction management.

        On success: COMMIT.
        On exception: ROLLBACK.
        """
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._return_connection(conn)

    def execute(
        self,
        query: str,
        params: Tuple = (),
        fetch: bool = True,
    ) -> Dict[str, Any]:
        """Execute a single SQL statement.

        Returns:
            Dict with 'rows' (list of dicts) for SELECT,
            or 'affected_rows' and 'lastrowid' for DML.
        """
        with self.connection() as conn:
            cursor = conn.execute(query, params)  # nosemgrep: sqlalchemy-execute-raw-query
            if fetch and query.strip().upper().startswith("SELECT"):
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                return {"rows": rows, "row_count": len(rows)}
            conn.commit()
            return {
                "affected_rows": cursor.rowcount,
                "lastrowid": cursor.lastrowid,
            }

    def execute_script(self, script: str) -> Dict[str, Any]:
        """Execute a SQL script with multiple statements."""
        with self.connection() as conn:
            conn.executescript(script)
            conn.commit()
            statements = [s.strip() for s in script.split(";") if s.strip()]
            return {"script_lines": len(statements)}

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        with self.connection() as conn:
            cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            return cursor.fetchone() is not None

    def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        """Get the schema of a table."""
        # SECURITY: Validate table_name before interpolation into PRAGMA
        import re
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
            raise ValueError(f"Invalid table name: {table_name!r}")
        with self.connection() as conn:
            cursor = conn.execute(f'PRAGMA table_info("{table_name}")')  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier
            columns = ["cid", "name", "type", "notnull", "dflt_value", "pk"]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close_all(self) -> None:
        """Close all connections in the pool."""
        for conn in self._pool:
            try:
                conn.close()
            except Exception:
                pass
        self._pool.clear()

    # ── Private methods ──────────────────────────────────────

    def _get_connection(self) -> Any:
        """Get a connection from the pool or create a new one."""
        if self._pool:
            return self._pool.pop()

        if self._encrypted and HAS_SQLCIPHER:
            key = self._passphrase
            if self._hardware_bind:
                key = self._derive_hardware_key(key)
            conn = get_sqlcipher_connection(
                self._db_path,
                key,
                kdf_iterations=self._kdf_iterations,
                cipher_page_size=self._cipher_page_size,
                row_factory=None,  # We set row_factory after PRAGMAs
                apply_pragmas=False,  # We set up PRAGMAs ourselves
            )
            # Apply adapter-specific PRAGMAs
            self._setup_sqlcipher_pragmas(conn)
            conn.row_factory = sqlite3.Row
        else:
            conn = sqlite3.connect(self._db_path)
            self._setup_sqlite(conn)

        conn.row_factory = sqlite3.Row
        return conn

    def _return_connection(self, conn: Any) -> None:
        """Return a connection to the pool."""
        if len(self._pool) < self._pool_size:
            try:
                # Verify connection is still alive
                conn.execute("SELECT 1")  # nosemgrep: sqlalchemy-execute-raw-query
                self._pool.append(conn)
                return
            except Exception:
                pass
        try:
            conn.close()
        except Exception:
            pass

    def _setup_sqlcipher_pragmas(self, conn: Any) -> None:
        """Apply additional PRAGMAs specific to the adapter after key setup.

        The key and cipher PRAGMAs are already set by sqlcipher_helper.
        Here we add WAL mode and ARM/mobile optimizations.
        """
        conn.execute("PRAGMA journal_mode = WAL")  # nosemgrep: sqlalchemy-execute-raw-query
        conn.execute("PRAGMA synchronous = NORMAL")  # nosemgrep: sqlalchemy-execute-raw-query
        conn.execute("PRAGMA cache_size = -8000")  # 8MB  # nosemgrep: sqlalchemy-execute-raw-query
        logger.info("SQLCipherAdapter: Encrypted connection established (%s)", self._db_path)

    def _setup_sqlite(self, conn: Any) -> None:
        """Configure standard SQLite PRAGMAs for unencrypted connection."""
        conn.execute("PRAGMA journal_mode = WAL")  # nosemgrep: sqlalchemy-execute-raw-query
        conn.execute("PRAGMA synchronous = NORMAL")  # nosemgrep: sqlalchemy-execute-raw-query
        conn.execute("PRAGMA cache_size = -8000")  # nosemgrep: sqlalchemy-execute-raw-query
        conn.execute("PRAGMA busy_timeout = 5000")  # nosemgrep: sqlalchemy-execute-raw-query
        conn.execute("PRAGMA mmap_size = 67108864")  # 64MB  # nosemgrep: sqlalchemy-execute-raw-query
        if not self._encrypted:
            logger.debug("SQLCipherAdapter: Unencrypted SQLite connection (%s)", self._db_path)

    @staticmethod
    def _derive_hardware_key(passphrase: str) -> str:
        """Derive a key bound to hardware fingerprint.

        Combines passphrase with CPU/disk/memory identifiers
        to ensure the database can only be opened on this machine.
        """
        import platform

        fingerprint_parts = [
            passphrase,
            platform.machine(),
            platform.processor(),
            str(os.cpu_count()),
        ]
        fingerprint = "|".join(fingerprint_parts)
        return hashlib.sha256(fingerprint.encode()).hexdigest()
