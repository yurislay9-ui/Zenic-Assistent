"""
ZENIC-AGENTS - Database Initializer v16 (Optimized for ARM)

Inicializa todas las bases de datos SQLite con:
- WAL mode para concurrencia sin locks
- Connection pooling para no abrir/cerrar constantemente
- PRAGMA optimizados para ARM (menos memoria, mas eficiencia)
- Indice en theorem_cache para skeleton_hash lookups rapidos

Compatible con Termux + proot-distro (Debian ARM).

.. deprecated:: FASE 1.3
   The connection pool functions (get_connection, write_lock, close_all_connections)
   are deprecated in favor of FastPool (src.core.shared.fast_connection_pool).
   Only initialize_databases() and utility functions (get_data_dir, get_db_path)
   should continue to be used for table creation.

   Migration guide:
   - get_connection(db) → fast_pool.get(db)
   - write_lock(db) → fast_pool.write(db)
   - close_all_connections() → fast_pool.close_all()

   db_initializer will be fully removed once all consumers migrate to FastPool.
"""

import sqlite3
import threading
from pathlib import Path
from typing import Optional
import os
import logging
import atexit

# Try to import ReadWriteLock for better concurrent access
# Per-database ReadWriteLock instances prevent cross-DB contention:
# a write lock for one DB no longer blocks reads on all others.
try:
    from src.core.patterns.concurrency import ReadWriteLock
    _HAS_RW_LOCK = True
except ImportError:
    _HAS_RW_LOCK = False

# Import SQLCipher helper for encrypted database connections
from src.core.shared.sqlcipher_helper import (
    HAS_SQLCIPHER as _HAS_SQLCIPHER,
    get_sqlcipher_connection as _get_sqlcipher_connection,
    is_sqlcipher_available,
)

logger = logging.getLogger(__name__)

__all__ = [
    "get_data_dir", "get_db_path", "get_projects_dir", "get_connection",
    "get_encrypted_connection", "is_encryption_enabled",
    "close_all_connections", "write_lock", "initialize_databases",
]

# ============================================================
#  CONNECTION POOL - Reutiliza conexiones SQLite
# ============================================================

_db_connections = {}       # {db_name: sqlite3.Connection}
_db_write_locks = {}       # {db_name: threading.Lock} — one lock per connection for write ops
_db_rw_locks = {}          # {db_name: ReadWriteLock} — per-DB rw lock when available
_db_lock = threading.Lock()

# Environment variable for enabling SQLCipher encryption on all connections
_ZENIC_DB_PASSPHRASE_ENV = "ZENIC_DB_PASSPHRASE"


def _optimize_pragma(conn):
    """
    Aplica PRAGMA optimizados para rendimiento en ARM.

    WAL mode: Permite lecturas concurrentes sin bloquear escrituras.
    cache_size: -8192 = 8MB cache (doubled from 4MB)
    synchronous NORMAL: Mas rapido que FULL, seguro con WAL
    temp_store MEMORY: Tablas temporales en RAM
    mmap_size: Memory-mapped I/O para lecturas grandes
    """
    conn.execute("PRAGMA journal_mode=WAL")  # nosemgrep: sqlalchemy-execute-raw-query
    conn.execute("PRAGMA cache_size=-8192")      # 8MB cache (doubled from 4MB)  # nosemgrep: sqlalchemy-execute-raw-query
    conn.execute("PRAGMA synchronous=NORMAL")     # Mas rapido con WAL  # nosemgrep: sqlalchemy-execute-raw-query
    conn.execute("PRAGMA temp_store=MEMORY")      # Temp en RAM  # nosemgrep: sqlalchemy-execute-raw-query
    conn.execute("PRAGMA mmap_size=67108864")     # 64MB mmap  # nosemgrep: sqlalchemy-execute-raw-query
    conn.execute("PRAGMA wal_autocheckpoint=1000") # Auto-checkpoint cada 1000 frames  # nosemgrep: sqlalchemy-execute-raw-query
    conn.execute("PRAGMA busy_timeout=5000")       # 5s timeout para locks  # nosemgrep: sqlalchemy-execute-raw-query
    conn.execute("PRAGMA foreign_keys=ON")         # Enforce referential integrity  # nosemgrep: sqlalchemy-execute-raw-query


def is_encryption_enabled() -> bool:
    """Check whether SQLCipher encryption is available and a passphrase is set.

    Returns True only when BOTH conditions are met:
      1. A SQLCipher library (pysqlcipher3 or sqlcipher3) is importable
      2. The ``ZENIC_DB_PASSPHRASE`` environment variable is non-empty

    When this returns True, ``get_connection()`` will automatically use
    SQLCipher for all new database connections.
    """
    return _HAS_SQLCIPHER and bool(os.environ.get(_ZENIC_DB_PASSPHRASE_ENV, ""))


def get_data_dir() -> Path:
    if 'ANDROID_ARGUMENT' in os.environ:
        try:
            from android.storage import app_storage_path  # type: ignore[import-unresolved]
            data_dir = Path(app_storage_path()) / "zenic_data"
        except Exception:
            data_dir = Path.home() / ".zenic_agents" / "data"
    else:
        data_dir = Path.home() / ".zenic_agents" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_db_path(db_name: str) -> str:
    return str(get_data_dir() / db_name)


def get_projects_dir() -> Path:
    p = get_data_dir() / "projects"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_encrypted_connection(
    db_name: str,
    passphrase: str = "",
) -> sqlite3.Connection:
    """Create an encrypted database connection using SQLCipher.

    When SQLCipher is available and a non-empty passphrase is provided,
    returns an AES-256 encrypted connection.  Otherwise falls back to
    plain SQLite with a warning log.

    Args:
        db_name: Database filename (e.g. ``"graph_ast.sqlite"``).
        passphrase: Encryption key.  If empty and the env-var
            ``ZENIC_DB_PASSPHRASE`` is set, that value is used instead.

    Returns:
        An open ``sqlite3.Connection`` (encrypted or plain).
    """
    effective_passphrase = passphrase or os.environ.get(_ZENIC_DB_PASSPHRASE_ENV, "")
    path = get_db_path(db_name)

    if effective_passphrase:
        conn = _get_sqlcipher_connection(
            path,
            effective_passphrase,
            kdf_iterations=64000,
            cipher_page_size=4096,
            apply_pragmas=False,
        )
        _optimize_pragma(conn)
        conn.row_factory = sqlite3.Row
        if _HAS_SQLCIPHER:
            logger.info("get_encrypted_connection: SQLCipher AES-256 for '%s'", db_name)
        return conn

    # Fallback: plain SQLite (no passphrase provided)
    conn = sqlite3.connect(path, check_same_thread=False)
    _optimize_pragma(conn)
    conn.row_factory = sqlite3.Row
    return conn


def get_connection(db_name: str) -> sqlite3.Connection:
    """
    Obtiene una conexion del pool. Reutiliza conexiones existentes.

    .. deprecated:: FASE 1.3
       Use FastPool.get(db_name) instead for better thread-local caching,
       3-layer connection management, and reduced SQLITE_BUSY contention.

       This function is kept for backward compatibility with existing consumers
       (graph_ast, theorem_cache, merkle_ledger, request_log) that have not yet
       migrated to FastPool.

    The pool mantiene una conexion por DB, thread-safe con lock.
    Si la conexion esta rota, crea una nueva.

    When ``is_encryption_enabled()`` is True (SQLCipher available +
    ZENIC_DB_PASSPHRASE set), new connections will use SQLCipher
    encryption automatically.

    Uses ReadWriteLock for better concurrent read access when available,
    falling back to a simple threading.Lock otherwise.

    IMPORTANT: For write operations, use the connection's write lock
    via `with db_initializer.write_lock(db_name):` to ensure thread safety.
    """
    import warnings
    warnings.warn(
        "db_initializer.get_connection() is deprecated since FASE 1.3. "
        "Use FastPool.get(db_name) instead for better connection management.",
        DeprecationWarning,
        stacklevel=2,
    )
    key = db_name
    # Use per-DB ReadWriteLock read context for concurrent read access
    if _HAS_RW_LOCK and key in _db_rw_locks:
        ctx = _db_rw_locks[key].acquire_read()
    elif _HAS_RW_LOCK:
        # First access to this DB — create its per-DB lock
        with _db_lock:
            if key not in _db_rw_locks:
                _db_rw_locks[key] = ReadWriteLock()
            ctx = _db_rw_locks[key].acquire_read()
    else:
        ctx = _db_lock
    with ctx:
        if key in _db_connections:
            conn = _db_connections[key]
            # Verificar que la conexion sigue viva
            try:
                conn.execute("SELECT 1")  # nosemgrep: sqlalchemy-execute-raw-query
                return conn
            except sqlite3.Error:
                # Conexion rota, crear nueva
                del _db_connections[key]

        # Use encrypted connection when encryption is enabled
        if is_encryption_enabled():
            conn = get_encrypted_connection(db_name)
        else:
            path = get_db_path(db_name)
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            _optimize_pragma(conn)

        _db_connections[key] = conn
        _db_write_locks[key] = threading.Lock()
        return conn


def close_all_connections():
    """Cierra todas las conexiones del pool (para shutdown limpio)."""
    with _db_lock:
        for key, conn in list(_db_connections.items()):
            try:
                conn.close()
            except Exception as e:
                logger.debug(f"close_all_connections: Failed to close connection: {e}")
        _db_connections.clear()
        _db_write_locks.clear()
        _db_rw_locks.clear()


# Register cleanup on process exit to prevent leaked DB connections
atexit.register(close_all_connections)


class write_lock:
    """
    Context manager to acquire the per-connection write lock.

    Uses ReadWriteLock for write preference when available,
    falling back to simple threading.Lock otherwise.

    Usage:
        conn = get_connection("graph_ast.sqlite")
        with write_lock("graph_ast.sqlite"):
            conn.execute("INSERT INTO ...")  # nosemgrep: sqlalchemy-execute-raw-query
            conn.commit()

    This ensures that only one thread writes to a given database at a time,
    preventing 'database is locked' errors and data corruption.
    """

    def __init__(self, db_name: str):
        self._db_name = db_name
        self._rw_ctx = None

    def __enter__(self):
        if _HAS_RW_LOCK:
            # Ensure per-DB ReadWriteLock exists
            if self._db_name not in _db_rw_locks:
                with _db_lock:
                    if self._db_name not in _db_rw_locks:
                        _db_rw_locks[self._db_name] = ReadWriteLock()
            self._rw_ctx = _db_rw_locks[self._db_name].acquire_write()
            self._rw_ctx.__enter__()
        else:
            lock = _db_write_locks.get(self._db_name)
            if lock is not None:
                lock.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._rw_ctx is not None:
            self._rw_ctx.__exit__(exc_type, exc_val, exc_tb)
            self._rw_ctx = None
        else:
            lock = _db_write_locks.get(self._db_name)
            if lock is not None:
                lock.release()
        return False


def initialize_databases():
    """Crea todas las tablas SQLite con esquemas completos v16 + indices + PRAGMA."""

    # Graph AST (Phase 2: tenant-aware)
    conn = get_connection("graph_ast.sqlite")
    conn.execute("""CREATE TABLE IF NOT EXISTS ast_nodes (  # nosemgrep: sqlalchemy-execute-raw-query
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT NOT NULL,
        node_type TEXT NOT NULL,
        name TEXT NOT NULL,
        start_byte INTEGER NOT NULL,
        end_byte INTEGER NOT NULL,
        content_hash TEXT NOT NULL,
        docstring TEXT,
        complexity INTEGER DEFAULT 1,
        connections TEXT DEFAULT '[]',
        tenant_id TEXT NOT NULL DEFAULT '__anonymous__',
        UNIQUE(file_path, name, node_type, tenant_id))""")
    # Indice para busquedas rapidas por nombre (usado por MacroRouter)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ast_name ON ast_nodes(name)")  # nosemgrep: sqlalchemy-execute-raw-query
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ast_type ON ast_nodes(node_type)")  # nosemgrep: sqlalchemy-execute-raw-query
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ast_tenant ON ast_nodes(tenant_id)")  # nosemgrep: sqlalchemy-execute-raw-query
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ast_tenant_file ON ast_nodes(tenant_id, file_path)")  # nosemgrep: sqlalchemy-execute-raw-query
    conn.commit()
    # Migrate: add tenant_id column if it doesn't exist (for existing databases)
    try:
        # Tenant module removed — skip tenant isolation migration
        # from src.core.tenant._isolation import TenantIsolation
        # TenantIsolation.migrate_add_tenant_id(conn, "ast_nodes", "__anonymous__")
        pass
    except Exception as e:
        logger.debug("ast_nodes tenant migration skipped: %s", e)

    # Theorem Cache
    conn = get_connection("theorem_cache.sqlite")
    conn.execute("""CREATE TABLE IF NOT EXISTS theorems (  # nosemgrep: sqlalchemy-execute-raw-query
        structural_hash TEXT NOT NULL,
        operation TEXT NOT NULL,
        goal TEXT NOT NULL,
        proof_result TEXT NOT NULL,
        solution_payload TEXT,
        skeleton_hash TEXT,
        hit_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        tenant_id TEXT NOT NULL DEFAULT '__anonymous__',
        PRIMARY KEY (structural_hash, tenant_id))""")
    # Indice para skeleton hash lookups (O(1) bypass experiencial)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skeleton ON theorems(skeleton_hash)")  # nosemgrep: sqlalchemy-execute-raw-query
    conn.execute("CREATE INDEX IF NOT EXISTS idx_theorems_tenant ON theorems(tenant_id)")  # nosemgrep: sqlalchemy-execute-raw-query
    conn.commit()
    # Migrate: add tenant_id column if it doesn't exist (for existing databases)
    try:
        # Tenant module removed — skip tenant isolation migration
        # from src.core.tenant._isolation import TenantIsolation
        # TenantIsolation.migrate_add_tenant_id(conn, "theorems", "__anonymous__")
        pass
    except Exception as e:
        logger.debug("Theorems tenant migration skipped: %s", e)

    # Merkle Ledger
    conn = get_connection("merkle_ledger.sqlite")
    conn.execute("""CREATE TABLE IF NOT EXISTS ledger (  # nosemgrep: sqlalchemy-execute-raw-query
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT NOT NULL,
        hash_sha256 TEXT NOT NULL,
        parent_hash TEXT NOT NULL,
        operation TEXT NOT NULL,
        timestamp REAL NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT '__anonymous__')""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_file ON ledger(file_path)")  # nosemgrep: sqlalchemy-execute-raw-query
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_tenant ON ledger(tenant_id)")  # nosemgrep: sqlalchemy-execute-raw-query
    conn.commit()
    # Migrate: add tenant_id column if it doesn't exist (for existing databases)
    try:
        # Tenant module removed — skip tenant isolation migration
        # from src.core.tenant._isolation import TenantIsolation
        # TenantIsolation.migrate_add_tenant_id(conn, "ledger", "__anonymous__")
        pass
    except Exception as e:
        logger.debug("Ledger tenant migration skipped: %s", e)

    # Request Log (Phase 2: tenant-aware)
    conn = get_connection("request_log.sqlite")
    conn.execute("""CREATE TABLE IF NOT EXISTS requests (  # nosemgrep: sqlalchemy-execute-raw-query
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL,
        model TEXT,
        operation TEXT,
        goal TEXT,
        route TEXT,
        status TEXT,
        processing_time_ms INTEGER,
        solver_status TEXT,
        mcts_simulations INTEGER DEFAULT 0,
        cache_hit INTEGER DEFAULT 0,
        tenant_id TEXT NOT NULL DEFAULT '__anonymous__',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_time ON requests(created_at)")  # nosemgrep: sqlalchemy-execute-raw-query
    conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_tenant ON requests(tenant_id)")  # nosemgrep: sqlalchemy-execute-raw-query
    conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_tenant_time ON requests(tenant_id, created_at)")  # nosemgrep: sqlalchemy-execute-raw-query
    conn.commit()
    # Migrate: add tenant_id column if it doesn't exist (for existing databases)
    try:
        # Tenant module removed — skip tenant isolation migration
        # from src.core.tenant._isolation import TenantIsolation
        # TenantIsolation.migrate_add_tenant_id(conn, "requests", "__anonymous__")
        pass
    except Exception as e:
        logger.debug("Requests tenant migration skipped: %s", e)

    logger.info("Databases initialized with WAL mode + PRAGMA optimizations")
