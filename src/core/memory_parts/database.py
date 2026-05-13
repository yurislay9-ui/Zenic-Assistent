"""
ZENIC-AGENTS - SmartMemory Database Mixin

DB initialization, migration, connections, WAL mode, vacuum, and table eviction.
"""

import os
import time
import json
import sqlite3
import logging
from typing import List

from .types import DB_DIR, DB_PATH, logger

class DatabaseMixin:
    """
    Mixin providing DB initialization, migration, connections, WAL mode,
    vacuum, and table eviction methods for SmartMemory.
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
        """
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")  # Faster than FULL, safe with WAL
                conn.execute("PRAGMA cache_size=-4096")  # 4MB cache for mobile
                conn.execute("PRAGMA temp_store=MEMORY")  # Temp tables in RAM
            logger.info("SmartMemory: WAL mode enabled (optimized for mobile)")
        except Exception as e:
            logger.warning(f"SmartMemory: WAL mode failed, using default: {e}")

    def _maybe_vacuum(self):
        """Ejecuta VACUUM periódicamente para prevenir bloat en el almacenamiento.

        En un teléfono, el espacio de almacenamiento es limitado y SQLite
        puede crecer mucho si no se compacta. VACUUM reconstruye la BD
        eliminando espacio muerto, pero es costoso → solo cada 24h.
        """
        now = time.time()
        if now - self._last_vacuum_time < self.VACUUM_INTERVAL_S:
            return

        try:
            db_size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
            if db_size_mb < 5.0:  # Only vacuum if DB > 5MB
                return

            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.execute("VACUUM")

            self._last_vacuum_time = now
            new_size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
            logger.info(
                f"SmartMemory: VACUUM complete ({db_size_mb:.1f}MB → {new_size_mb:.1f}MB)"
            )
        except Exception as e:
            logger.debug(f"SmartMemory: VACUUM failed (will retry later): {e}")

    def _get_connection(self) -> sqlite3.Connection:
        """Obtiene una conexión SQLite optimizada para móvil."""
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-4096")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA busy_timeout=5000")  # 5s timeout for concurrent access
        return conn

    def _init_db(self):
        """Crea tablas SQLite si no existen (con tenant_id para multitenancy)."""
        conn = self._get_connection()
        try:
            conn.execute("""CREATE TABLE IF NOT EXISTS semantic_cache (
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
            conn.execute("""CREATE TABLE IF NOT EXISTS long_term_memory (
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
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_cache_hash 
                ON semantic_cache(query_hash)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_ltm_importance 
                ON long_term_memory(importance DESC)""")
            # Additional indexes for common mobile query patterns
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_cache_client_time
                ON semantic_cache(client_id, created_at DESC)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_ltm_client_success
                ON long_term_memory(client_id, success, importance DESC)""")

            # === Episodic Memory ===
            conn.execute("""CREATE TABLE IF NOT EXISTS episodic_memory (
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
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_episodic_type 
                ON episodic_memory(event_type)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_episodic_time 
                ON episodic_memory(created_at DESC)""")

            # === Procedural Memory ===
            conn.execute("""CREATE TABLE IF NOT EXISTS procedural_memory (
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
            conn.execute("""CREATE TABLE IF NOT EXISTS project_memory (
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
            conn.execute("""CREATE TABLE IF NOT EXISTS conversation_sessions (
                id TEXT PRIMARY KEY,
                started_at REAL DEFAULT 0,
                ended_at REAL DEFAULT 0,
                summary TEXT DEFAULT '',
                importance REAL DEFAULT 0.5,
                exchange_count INTEGER DEFAULT 0,
                client_id TEXT DEFAULT 'default',
                tenant_id TEXT DEFAULT '__anonymous__'
            )""")

            conn.commit()
        finally:
            conn.close()

        # Brecha B: Migrate existing tables that may not have client_id column
        self._migrate_add_client_id()

        # Brecha B: Create client_id indexes for all tables
        self._create_client_id_indexes()

        # Phase 2: Migrate existing tables that may not have tenant_id column
        self._migrate_add_tenant_id()

        # Phase 2: Create tenant_id indexes for all tables
        self._create_tenant_id_indexes()

    def _migrate_add_client_id(self):
        """Brecha B: Add client_id column to existing tables if missing."""
        tables = [
            "semantic_cache", "long_term_memory", "episodic_memory",
            "procedural_memory", "project_memory", "conversation_sessions",
        ]
        conn = self._get_connection()
        try:
            for table in tables:
                assert table in self._VALID_TABLES, f"Invalid table: {table}"
                try:
                    conn.execute(
                        f'ALTER TABLE "{table}" ADD COLUMN client_id TEXT DEFAULT \'default\''
                    )
                except sqlite3.OperationalError:
                    # Column already exists, ignore
                    pass
            conn.commit()
        finally:
            conn.close()

    def _create_client_id_indexes(self):
        """Brecha B: Create indexes on client_id for all tables."""
        tables = [
            "semantic_cache", "long_term_memory", "episodic_memory",
            "procedural_memory", "project_memory", "conversation_sessions",
        ]
        conn = self._get_connection()
        try:
            for table in tables:
                assert table in self._VALID_TABLES, f"Invalid table: {table}"
                conn.execute(
                    f'CREATE INDEX IF NOT EXISTS "idx_{table}_client" ON "{table}"(client_id)'
                )
            conn.commit()
        finally:
            conn.close()

    def _migrate_add_tenant_id(self):
        """Phase 2: Add tenant_id column to existing tables if missing.

        Uses ALTER TABLE to safely add the column. Default value is
        '__anonymous__' so that existing rows are grouped under the
        anonymous tenant, maintaining backward compatibility.
        """
        tables = [
            "semantic_cache", "long_term_memory", "episodic_memory",
            "procedural_memory", "project_memory", "conversation_sessions",
        ]
        conn = self._get_connection()
        try:
            # Validate DEFAULT_TENANT_ID contains no SQL-injectable characters
            _safe_default = self.DEFAULT_TENANT_ID
            if not _safe_default.isidentifier() and not all(c.isalnum() or c == '_' for c in _safe_default):
                raise ValueError(f"DEFAULT_TENANT_ID contains unsafe characters: {_safe_default!r}")
            for table in tables:
                assert table in self._VALID_TABLES, f"Invalid table: {table}"
                try:
                    conn.execute(
                        f'ALTER TABLE "{table}" ADD COLUMN tenant_id TEXT DEFAULT %s' % repr(_safe_default)
                    )
                    logger.info("SmartMemory: Added tenant_id column to '%s'", table)
                except sqlite3.OperationalError:
                    # Column already exists, ignore
                    pass
            conn.commit()
        finally:
            conn.close()

    def _create_tenant_id_indexes(self):
        """Phase 2: Create indexes on tenant_id for all tables.

        Composite indexes on (tenant_id, client_id) support the common
        query pattern of filtering by tenant first, then by client.
        """
        tables = [
            "semantic_cache", "long_term_memory", "episodic_memory",
            "procedural_memory", "project_memory", "conversation_sessions",
        ]
        conn = self._get_connection()
        try:
            for table in tables:
                assert table in self._VALID_TABLES, f"Invalid table: {table}"
                # Single-column index on tenant_id
                conn.execute(
                    f'CREATE INDEX IF NOT EXISTS "idx_{table}_tenant" ON "{table}"(tenant_id)'
                )
                # Composite index for tenant + client queries
                conn.execute(
                    f'CREATE INDEX IF NOT EXISTS "idx_{table}_tenant_client" ON "{table}"(tenant_id, client_id)'
                )
            conn.commit()
        finally:
            conn.close()

    def _evict_table(self, table_name: str, max_entries: int):
        """Evict oldest/least important entries from a table."""
        # SQL Injection protection: validate table_name against whitelist
        assert table_name in self._VALID_TABLES, f"Invalid table: {table_name}"
        if table_name not in self._VALID_TABLES:
            logger.warning(f"SmartMemory._evict_table: Invalid table name '{table_name}' rejected")
            return
        with sqlite3.connect(DB_PATH) as conn:
            count = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
            if count > max_entries:
                conn.execute(f'DELETE FROM "{table_name}" WHERE id IN (SELECT id FROM "{table_name}" ORDER BY importance ASC, created_at ASC LIMIT ?)', (count - max_entries + 10,))
