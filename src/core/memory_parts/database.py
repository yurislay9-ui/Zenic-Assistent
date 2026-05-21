"""
ZENIC-AGENTS - SmartMemory Database Mixin

DB initialization, migration, connections, WAL mode, vacuum, and table eviction.

FASE 1.1 Performance Fix:
- Replaced all raw sqlite3.connect(DB_PATH) calls with FastPool.
- FastPool provides thread-local cached connections, eliminating competing
  connection systems that cause SQLITE_BUSY errors under concurrent access.
- PRAGMAs are now applied automatically by FastPool when creating connections,
  so _get_connection() and _enable_wal_mode() no longer apply PRAGMAs manually.
- Write operations use smart_memory_pool.write() for thread-safe auto-commit.
- Connections are NOT closed — the pool manages their lifecycle.
"""

import os
import time
import json
import sqlite3
import logging
from typing import List

from .types import DB_DIR, DB_PATH, logger
from .pool import smart_memory_pool, SMART_MEMORY_DB

class DatabaseMixin:
    """
    Mixin providing DB initialization, migration, connections, WAL mode,
    vacuum, and table eviction methods for SmartMemory.

    FASE 1.1: All database access now goes through smart_memory_pool
    instead of raw sqlite3.connect() calls.
    """

    # VACUUM interval: every 24 hours to prevent DB bloat on phone storage
    VACUUM_INTERVAL_S = 86400  # 24 hours

    # Default tenant_id for anonymous/unauthenticated access
    DEFAULT_TENANT_ID = "__anonymous__"

    # Whitelist of allowed table names to prevent SQL injection
    _VALID_TABLES = frozenset({
        "semantic_cache", "long_term_memory", "working_memory",
        "episodic_memory", "procedural_memory", "project_memory",
        "conversation_sessions",
    })

    def _enable_wal_mode(self):
        """Habilita WAL mode para mejor rendimiento concurrente en móvil.

        WAL (Write-Ahead Logging) permite lecturas sin bloquear escrituras,
        reduce la escritura al disco (importante para flash del teléfono),
        y mejora el rendimiento de consultas frecuentes como cache lookup.

        FASE 1.1: WAL mode is now handled by FastPool's PRAGMA configuration.
        FastPool applies WAL, synchronous=NORMAL, cache_size=-8192,
        temp_store=MEMORY, mmap_size, wal_autocheckpoint, and busy_timeout
        on every new connection. This method is kept for backward
        compatibility but is now effectively a no-op.
        """
        # FastPool already applies all WAL-related PRAGMAs when creating
        # connections. The pool's PRAGMAs are even more optimized than the
        # previous manual ones (8MB cache vs 4MB, mmap_size, wal_autocheckpoint,
        # foreign_keys, etc.).
        logger.debug("SmartMemory: WAL mode handled by FastPool (no-op)")

    def _maybe_vacuum(self):
        """Ejecuta VACUUM periódicamente para prevenir bloat en el almacenamiento.

        En un teléfono, el espacio de almacenamiento es limitado y SQLite
        puede crecer mucho si no se compacta. VACUUM reconstruye la BD
        eliminando espacio muerto, pero es costoso → solo cada 24h.

        FASE 1.1: Uses smart_memory_pool.write() instead of raw connection,
        ensuring no SQLITE_BUSY conflicts during VACUUM.
        """
        now = time.time()
        if now - self._last_vacuum_time < self.VACUUM_INTERVAL_S:
            return

        try:
            db_size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
            if db_size_mb < 5.0:  # Only vacuum if DB > 5MB
                return

            # FASE 1.1: Use pool's write() for VACUUM (requires exclusive access,
            # write lock prevents concurrent writers during checkpoint/vacuum)
            with smart_memory_pool.write(SMART_MEMORY_DB) as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # nosemgrep: sqlalchemy-execute-raw-query
                conn.execute("VACUUM")  # nosemgrep: sqlalchemy-execute-raw-query

            self._last_vacuum_time = now
            new_size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
            logger.info(
                f"SmartMemory: VACUUM complete ({db_size_mb:.1f}MB → {new_size_mb:.1f}MB)"
            )
        except Exception as e:
            logger.debug(f"SmartMemory: VACUUM failed (will retry later): {e}")

    def _get_connection(self) -> sqlite3.Connection:
        """Obtiene una conexión SQLite optimizada para móvil.

        FASE 1.1: Now uses FastPool instead of raw sqlite3.connect().
        PRAGMAs are applied automatically by FastPool when creating connections,
        so this method no longer applies them manually.
        The returned connection is managed by the pool — callers should NOT close it.
        """
        return smart_memory_pool.get(SMART_MEMORY_DB)

    def _init_db(self):
        """Crea tablas SQLite si no existen (con tenant_id para multitenancy).

        FASE 1.1: Uses smart_memory_pool.write() instead of _get_connection()
        + manual commit/close. The pool auto-commits and manages connections.
        """
        # FASE 1.1: Use pool's write() for DDL operations (auto-commit, write-locked)
        with smart_memory_pool.write(SMART_MEMORY_DB) as conn:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE TABLE IF NOT EXISTS semantic_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_hash TEXT NOT NULL,
                query_text TEXT NOT NULL,
                response_summary TEXT NOT NULL,
                operation TEXT DEFAULT '',
                goal TEXT DEFAULT '',
                importance REAL DEFAULT 0.5,
                embedding BLOB,
                created_at REAL DEFAULT 0,
                access_count INTEGER DEFAULT 0,
                session_id TEXT DEFAULT '',
                client_id TEXT DEFAULT 'default',
                tenant_id TEXT DEFAULT '__anonymous__',
                UNIQUE(query_hash, tenant_id)
            )""")
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE TABLE IF NOT EXISTS long_term_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_text TEXT NOT NULL,
                solution_summary TEXT NOT NULL,
                operation TEXT DEFAULT '',
                goal TEXT DEFAULT '',
                importance REAL DEFAULT 0.5,
                success BOOLEAN DEFAULT 1,
                embedding BLOB,
                created_at REAL DEFAULT 0,
                access_count INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]',
                client_id TEXT DEFAULT 'default',
                tenant_id TEXT DEFAULT '__anonymous__'
            )""")
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE INDEX IF NOT EXISTS idx_cache_hash
                ON semantic_cache(query_hash)""")
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE INDEX IF NOT EXISTS idx_ltm_importance
                ON long_term_memory(importance DESC)""")
            # Additional indexes for common mobile query patterns
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE INDEX IF NOT EXISTS idx_cache_client_time
                ON semantic_cache(client_id, created_at DESC)""")
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE INDEX IF NOT EXISTS idx_ltm_client_success
                ON long_term_memory(client_id, success, importance DESC)""")

            # === Episodic Memory ===
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE TABLE IF NOT EXISTS episodic_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                description TEXT NOT NULL,
                context TEXT DEFAULT '',
                outcome TEXT DEFAULT '',
                importance REAL DEFAULT 0.5,
                embedding BLOB,
                created_at REAL DEFAULT 0,
                tags TEXT DEFAULT '[]',
                client_id TEXT DEFAULT 'default',
                tenant_id TEXT DEFAULT '__anonymous__'
            )""")
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE INDEX IF NOT EXISTS idx_episodic_type
                ON episodic_memory(event_type)""")
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE INDEX IF NOT EXISTS idx_episodic_time
                ON episodic_memory(created_at DESC)""")

            # === Procedural Memory ===
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE TABLE IF NOT EXISTS procedural_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_name TEXT NOT NULL UNIQUE,
                pattern_type TEXT DEFAULT 'strategy',
                description TEXT NOT NULL,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 0.0,
                steps TEXT DEFAULT '[]',
                embedding BLOB,
                created_at REAL DEFAULT 0,
                last_used REAL DEFAULT 0,
                client_id TEXT DEFAULT 'default',
                tenant_id TEXT DEFAULT '__anonymous__'
            )""")

            # === Project Memory ===
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE TABLE IF NOT EXISTS project_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL UNIQUE,
                project_type TEXT DEFAULT '',
                description TEXT DEFAULT '',
                path TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                entities TEXT DEFAULT '[]',
                endpoints TEXT DEFAULT '[]',
                config TEXT DEFAULT '{}',
                created_at REAL DEFAULT 0,
                updated_at REAL DEFAULT 0,
                notes TEXT DEFAULT '',
                client_id TEXT DEFAULT 'default',
                tenant_id TEXT DEFAULT '__anonymous__'
            )""")

            # === Conversation Sessions ===
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE TABLE IF NOT EXISTS conversation_sessions (
                id TEXT PRIMARY KEY,
                started_at REAL DEFAULT 0,
                ended_at REAL DEFAULT 0,
                summary TEXT DEFAULT '',
                importance REAL DEFAULT 0.5,
                exchange_count INTEGER DEFAULT 0,
                client_id TEXT DEFAULT 'default',
                tenant_id TEXT DEFAULT '__anonymous__'
            )""")

            # write() auto-commits on exit — no explicit conn.commit() needed
        # Pool manages connections — no conn.close() needed

        # Brecha B: Migrate existing tables that may not have client_id column
        self._migrate_add_client_id()

        # Brecha B: Create client_id indexes for all tables
        self._create_client_id_indexes()

        # Phase 2: Migrate existing tables that may not have tenant_id column
        self._migrate_add_tenant_id()

        # Phase 2: Create tenant_id indexes for all tables
        self._create_tenant_id_indexes()

    def _migrate_add_client_id(self):
        """Brecha B: Add client_id column to existing tables if missing.

        FASE 1.1: Uses smart_memory_pool.write() instead of raw connection.
        """
        tables = [
            "semantic_cache", "long_term_memory", "episodic_memory",
            "procedural_memory", "project_memory", "conversation_sessions",
        ]
        # FASE 1.1: Use pool's write() for migration DDL (auto-commit, write-locked)
        with smart_memory_pool.write(SMART_MEMORY_DB) as conn:
            for table in tables:
                assert table in self._VALID_TABLES, f"Invalid table: {table}"
                try:
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        f'ALTER TABLE "{table}" ADD COLUMN client_id TEXT DEFAULT \'default\''
                    )
                except sqlite3.OperationalError:
                    # Column already exists, ignore
                    pass
            # write() auto-commits on exit

    def _create_client_id_indexes(self):
        """Brecha B: Create indexes on client_id for all tables.

        FASE 1.1: Uses smart_memory_pool.write() instead of raw connection.
        """
        tables = [
            "semantic_cache", "long_term_memory", "episodic_memory",
            "procedural_memory", "project_memory", "conversation_sessions",
        ]
        # FASE 1.1: Use pool's write() for index creation (auto-commit)
        with smart_memory_pool.write(SMART_MEMORY_DB) as conn:
            for table in tables:
                assert table in self._VALID_TABLES, f"Invalid table: {table}"
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    f'CREATE INDEX IF NOT EXISTS "idx_{table}_client" ON "{table}"(client_id)'
                )
            # write() auto-commits on exit

    def _migrate_add_tenant_id(self):
        """Phase 2: Add tenant_id column to existing tables if missing.

        Uses ALTER TABLE to safely add the column. Default value is
        '__anonymous__' so that existing rows are grouped under the
        anonymous tenant, maintaining backward compatibility.

        FASE 1.1: Uses smart_memory_pool.write() instead of raw connection.
        """
        tables = [
            "semantic_cache", "long_term_memory", "episodic_memory",
            "procedural_memory", "project_memory", "conversation_sessions",
        ]
        # FASE 1.1: Use pool's write() for migration DDL (auto-commit, write-locked)
        with smart_memory_pool.write(SMART_MEMORY_DB) as conn:
            # Validate DEFAULT_TENANT_ID contains no SQL-injectable characters
            _safe_default = self.DEFAULT_TENANT_ID
            if not _safe_default.isidentifier() and not all(c.isalnum() or c == '_' for c in _safe_default):
                raise ValueError(f"DEFAULT_TENANT_ID contains unsafe characters: {_safe_default!r}")
            for table in tables:
                assert table in self._VALID_TABLES, f"Invalid table: {table}"
                try:
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        f'ALTER TABLE "{table}" ADD COLUMN tenant_id TEXT DEFAULT %s' % repr(_safe_default)
                    )
                    logger.info("SmartMemory: Added tenant_id column to '%s'", table)
                except sqlite3.OperationalError:
                    # Column already exists, ignore
                    pass
            # write() auto-commits on exit

    def _create_tenant_id_indexes(self):
        """Phase 2: Create indexes on tenant_id for all tables.

        Composite indexes on (tenant_id, client_id) support the common
        query pattern of filtering by tenant first, then by client.

        FASE 1.1: Uses smart_memory_pool.write() instead of raw connection.
        """
        tables = [
            "semantic_cache", "long_term_memory", "episodic_memory",
            "procedural_memory", "project_memory", "conversation_sessions",
        ]
        # FASE 1.1: Use pool's write() for index creation (auto-commit)
        with smart_memory_pool.write(SMART_MEMORY_DB) as conn:
            for table in tables:
                assert table in self._VALID_TABLES, f"Invalid table: {table}"
                # Single-column index on tenant_id
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    f'CREATE INDEX IF NOT EXISTS "idx_{table}_tenant" ON "{table}"(tenant_id)'
                )
                # Composite index for tenant + client queries
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    f'CREATE INDEX IF NOT EXISTS "idx_{table}_tenant_client" ON "{table}"(tenant_id, client_id)'
                )
            # write() auto-commits on exit

    def _evict_table(self, table_name: str, max_entries: int):
        """Evict oldest/least important entries from a table.

        FASE 1.1: Uses smart_memory_pool.write() instead of raw connection,
        ensuring no SQLITE_BUSY conflicts during eviction.
        """
        # SQL Injection protection: validate table_name against whitelist
        assert table_name in self._VALID_TABLES, f"Invalid table: {table_name}"
        if table_name not in self._VALID_TABLES:
            logger.warning(f"SmartMemory._evict_table: Invalid table name '{table_name}' rejected")
            return
        # SECURITY: table_name validated against _VALID_TABLES whitelist above;
        # row limit uses ? parameterization
        # FASE 1.1: Use pool's write() for read + delete (auto-commit)
        with smart_memory_pool.write(SMART_MEMORY_DB) as conn:
            count = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier
            if count > max_entries:
                conn.execute(f'DELETE FROM "{table_name}" WHERE id IN (SELECT id FROM "{table_name}" ORDER BY importance ASC, created_at ASC LIMIT ?)', (count - max_entries + 10,))  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier
            # write() auto-commits on exit
