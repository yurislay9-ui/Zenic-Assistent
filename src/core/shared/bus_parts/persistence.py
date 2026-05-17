"""
ZENIC-AGENTS — Shared Memory Bus: Persistence Layer.

SQLite WAL-mode backend for durable storage with batched writes
to minimise fsync overhead.
"""

import json
import logging
import re
import sqlite3
import threading
from typing import List, Tuple

from .types import BusMessage, _DB_CACHE_SIZE, _DB_MMAP_SIZE, _FLUSH_BATCH_SIZE

# SQL Injection protection: validate identifiers before interpolation
_SAFE_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
_SAFE_TABLES = frozenset({"mailbox_messages", "shared_state", "ring_buffer_snapshots"})

logger = logging.getLogger(__name__)


class PersistenceLayer:
    """SQLite WAL-mode backend for durable storage.

    Manages three tables: ``mailbox_messages``, ``shared_state``,
    ``ring_buffer_snapshots``. Writes are batched (50 ms or 100 entries)
    to minimise fsync overhead.

    Args:
        db_path: Path to the SQLite database file.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS mailbox_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT NOT NULL,
        recipient TEXT NOT NULL,
        msg_type INTEGER NOT NULL,
        priority INTEGER NOT NULL,
        payload TEXT NOT NULL,
        timestamp REAL NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT 'default',
        ttl_seconds REAL NOT NULL DEFAULT 300.0,
        correlation_id TEXT DEFAULT '',
        created_at REAL DEFAULT (strftime('%s','now'))
    );
    CREATE INDEX IF NOT EXISTS idx_mm_recipient_priority
        ON mailbox_messages(recipient, priority);
    CREATE INDEX IF NOT EXISTS idx_mm_tenant
        ON mailbox_messages(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_mm_timestamp
        ON mailbox_messages(timestamp);

    CREATE TABLE IF NOT EXISTS shared_state (
        namespace TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT 'default',
        updated_at REAL NOT NULL,
        ttl_seconds REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (namespace, key, tenant_id)
    );

    CREATE TABLE IF NOT EXISTS ring_buffer_snapshots (
        slot_index INTEGER PRIMARY KEY,
        data BLOB,
        tenant_id TEXT NOT NULL DEFAULT 'default',
        timestamp REAL NOT NULL
    );
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._write_lock = threading.Lock()  # guards pending queues
        self._db_lock = threading.Lock()  # guards SQLite connection
        # Pending batches
        self._pending_messages: List[BusMessage] = []
        self._pending_state: List[Tuple[str, str, str, str, float, float]] = []
        self._pending_ring: List[Tuple[int, bytes, str, float]] = []
        self._conn = self._open()
        self._init_schema()

    # ── Connection ──

    def _open(self) -> sqlite3.Connection:
        """Open a connection with WAL-mode and tuned PRAGMAs."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")  # nosemgrep: sqlalchemy-execute-raw-query
        # SECURITY: PRAGMA statements cannot use ? parameterization in sqlite3.
        # _DB_CACHE_SIZE and _DB_MMAP_SIZE are module-level integer constants
        # validated by type (int). No user input flows here.
        assert isinstance(_DB_CACHE_SIZE, int), f"Invalid cache_size: {_DB_CACHE_SIZE}"
        assert isinstance(_DB_MMAP_SIZE, int), f"Invalid mmap_size: {_DB_MMAP_SIZE}"
        conn.execute(f"PRAGMA cache_size={_DB_CACHE_SIZE}")  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier
        conn.execute(f"PRAGMA mmap_size={_DB_MMAP_SIZE}")  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier
        conn.execute("PRAGMA synchronous=NORMAL")  # nosemgrep: sqlalchemy-execute-raw-query
        conn.execute("PRAGMA temp_store=MEMORY")  # nosemgrep: sqlalchemy-execute-raw-query
        return conn

    def _init_schema(self) -> None:
        """Create tables and indexes if they don't exist."""
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()

    # ── Enqueue ──

    def enqueue_message(self, msg: BusMessage) -> None:
        """Stage a message for batched write."""
        with self._write_lock:
            self._pending_messages.append(msg)

    def enqueue_state(self, entry: Tuple[str, str, str, str, float, float]) -> None:
        """Stage a state entry for batched write."""
        with self._write_lock:
            self._pending_state.append(entry)

    def enqueue_ring(self, entry: Tuple[int, bytes, str, float]) -> None:
        """Stage a ring-buffer slot for batched write."""
        with self._write_lock:
            self._pending_ring.append(entry)

    # ── Flush ──

    def flush(self) -> None:
        """Flush all pending writes to SQLite in batched transactions."""
        with self._write_lock:
            msgs = self._pending_messages[:]
            states = self._pending_state[:]
            rings = self._pending_ring[:]
            self._pending_messages.clear()
            self._pending_state.clear()
            self._pending_ring.clear()

        if not msgs and not states and not rings:
            return

        # Serialise messages outside the DB lock to minimise contention
        msg_rows = [
            (
                m.sender, m.recipient, int(m.msg_type),
                int(m.priority),
                json.dumps(m.payload, default=str),
                m.timestamp, m.tenant_id,
                m.ttl_seconds, m.correlation_id,
            )
            for m in msgs
        ]

        with self._db_lock:
            try:
                # Mailbox messages — chunked to avoid huge transactions
                for offset in range(0, len(msg_rows), _FLUSH_BATCH_SIZE):
                    chunk = msg_rows[offset:offset + _FLUSH_BATCH_SIZE]
                    self._conn.executemany(
                        """INSERT INTO mailbox_messages
                           (sender, recipient, msg_type, priority, payload,
                            timestamp, tenant_id, ttl_seconds, correlation_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        chunk,
                    )
                    self._conn.commit()

                # Shared state (upsert) — chunked
                for offset in range(0, len(states), _FLUSH_BATCH_SIZE):
                    chunk = states[offset:offset + _FLUSH_BATCH_SIZE]
                    self._conn.executemany(
                        """INSERT INTO shared_state
                           (namespace, key, value, tenant_id, updated_at, ttl_seconds)
                           VALUES (?, ?, ?, ?, ?, ?)
                           ON CONFLICT(namespace, key, tenant_id)
                           DO UPDATE SET value=excluded.value,
                                         updated_at=excluded.updated_at,
                                         ttl_seconds=excluded.ttl_seconds""",
                        chunk,
                    )
                    self._conn.commit()

                # Ring buffer snapshots — chunked
                for offset in range(0, len(rings), _FLUSH_BATCH_SIZE):
                    chunk = rings[offset:offset + _FLUSH_BATCH_SIZE]
                    self._conn.executemany(
                        """INSERT OR REPLACE INTO ring_buffer_snapshots
                           (slot_index, data, tenant_id, timestamp)
                           VALUES (?, ?, ?, ?)""",
                        chunk,
                    )
                    self._conn.commit()
            except Exception:
                logger.exception("PersistenceLayer flush failed")

    # ── Checkpoint ──

    def checkpoint(self) -> None:
        """Run WAL checkpoint to truncate the WAL file."""
        with self._db_lock:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                logger.exception("WAL checkpoint failed")

    # ── Purge ──

    def purge_tenant(self, tenant_id: str) -> int:
        """Delete all data for a tenant (GDPR compliance).

        Returns:
            Total number of rows deleted.
        """
        with self._db_lock:
            total = 0
            for table in ("mailbox_messages", "shared_state", "ring_buffer_snapshots"):
                # SECURITY: Validate table name against whitelist before interpolation
                assert table in _SAFE_TABLES, f"Invalid table name: {table}"
                try:
                    cursor = self._conn.execute(
                        f'DELETE FROM "{table}" WHERE tenant_id=?', (tenant_id,)
                    )
                    total += cursor.rowcount
                except Exception:
                    logger.exception("Purge failed for tenant=%s table=%s",
                                     tenant_id, table)
            self._conn.commit()
            return total

    # ── Lifecycle ──

    def close(self) -> None:
        """Flush remaining data and close the connection."""
        self.flush()
        with self._db_lock:
            try:
                self._conn.close()
            except Exception:
                logger.exception("Error closing PersistenceLayer connection")
