"""
ZENIC-AGENTS - DB Initializer Unit Tests

Tests for src/core/shared/db_initializer.py:
  - get_data_dir / get_db_path / get_projects_dir
  - Connection pool: get_connection, close_all_connections
  - write_lock context manager
  - initialize_databases (schema creation)
  - PRAGMA optimization
"""

import os
import sqlite3
import tempfile
import threading
from pathlib import Path

import pytest
from unittest.mock import patch, MagicMock

import src.core.shared.db_initializer as db_initializer_mod
from src.core.shared.db_initializer import (
    get_data_dir,
    get_db_path,
    get_projects_dir,
    get_connection,
    close_all_connections,
    write_lock,
    initialize_databases,
    _optimize_pragma,
    _db_connections,
    _db_write_locks,
    _db_lock,
    _HAS_RW_LOCK,
)


# ============================================================
#  FIXTURE: Isolated temp directory for DB operations
# ============================================================

@pytest.fixture(autouse=True)
def isolate_db():
    """Ensure each test uses an isolated temp data directory and clean pool."""
    tmpdir = tempfile.mkdtemp(prefix="zenic_test_dbinit_")
    original_get_data_dir = db_initializer_mod.get_data_dir

    def _patched_get_data_dir():
        p = Path(tmpdir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Patch on the module so all callers see it
    db_initializer_mod.get_data_dir = _patched_get_data_dir

    # Clear pool before test
    close_all_connections()

    yield tmpdir

    # Cleanup
    close_all_connections()
    db_initializer_mod.get_data_dir = original_get_data_dir

    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
#  GET_DATA_DIR / GET_DB_PATH / GET_PROJECTS_DIR TESTS
# ============================================================

class TestDirectoryFunctions:
    """Tests for get_data_dir, get_db_path, get_projects_dir."""

    def test_get_data_dir_returns_path(self):
        """get_data_dir should return a Path object."""
        result = db_initializer_mod.get_data_dir()
        assert isinstance(result, Path)

    def test_get_data_dir_creates_directory(self):
        """get_data_dir should create the directory if it doesn't exist."""
        result = db_initializer_mod.get_data_dir()
        assert result.exists()
        assert result.is_dir()

    def test_get_db_path_returns_string(self):
        """get_db_path should return a string path."""
        result = db_initializer_mod.get_db_path("test.sqlite")
        assert isinstance(result, str)
        assert result.endswith("test.sqlite")

    def test_get_db_path_under_data_dir(self):
        """get_db_path should be under the data directory."""
        result = db_initializer_mod.get_db_path("mydb.sqlite")
        data_dir = str(db_initializer_mod.get_data_dir())
        assert result.startswith(data_dir)

    def test_get_projects_dir_returns_path(self):
        """get_projects_dir should return a Path object."""
        result = db_initializer_mod.get_projects_dir()
        assert isinstance(result, Path)

    def test_get_projects_dir_creates_directory(self):
        """get_projects_dir should create the projects directory."""
        result = db_initializer_mod.get_projects_dir()
        assert result.exists()
        assert result.is_dir()
        assert result.name == "projects"


# ============================================================
#  CONNECTION POOL TESTS
# ============================================================

class TestConnectionPool:
    """Tests for get_connection and close_all_connections."""

    def test_get_connection_returns_sqlite_connection(self):
        """get_connection should return a sqlite3.Connection."""
        conn = get_connection("test_pool.sqlite")
        assert isinstance(conn, sqlite3.Connection)

    def test_get_connection_reuses_connection(self):
        """Should reuse the same connection for the same db_name."""
        conn1 = get_connection("test_reuse.sqlite")
        conn2 = get_connection("test_reuse.sqlite")
        assert conn1 is conn2

    def test_get_connection_different_db_names(self):
        """Different db_names should return different connections."""
        conn1 = get_connection("test_db1.sqlite")
        conn2 = get_connection("test_db2.sqlite")
        assert conn1 is not conn2

    def test_get_connection_has_row_factory(self):
        """Connection should have Row factory for dict-like access."""
        conn = get_connection("test_rowfactory.sqlite")
        assert conn.row_factory is sqlite3.Row

    def test_get_connection_creates_write_lock(self):
        """Getting a connection should create a corresponding write lock."""
        get_connection("test_lock.sqlite")
        assert "test_lock.sqlite" in _db_write_locks

    def test_close_all_connections(self):
        """close_all_connections should close and clear all connections."""
        get_connection("test_close1.sqlite")
        get_connection("test_close2.sqlite")
        assert len(_db_connections) > 0

        close_all_connections()
        assert len(_db_connections) == 0
        assert len(_db_write_locks) == 0

    def test_connection_recovery_after_broken(self):
        """Should create new connection if existing one is broken."""
        conn1 = get_connection("test_broken.sqlite")
        # Simulate broken connection by closing it externally
        conn1.close()

        # Should get a new connection
        conn2 = get_connection("test_broken.sqlite")
        assert conn2 is not conn1
        # Verify new connection works
        conn2.execute("SELECT 1")


# ============================================================
#  WRITE LOCK TESTS
# ============================================================

class TestWriteLock:
    """Tests for the write_lock context manager."""

    def test_write_lock_acquires_and_releases(self):
        """write_lock should acquire and release the lock properly."""
        get_connection("test_wl.sqlite")  # Ensure lock exists

        if _HAS_RW_LOCK:
            # When ReadWriteLock is available, write_lock uses the global
            # RW lock instead of the per-connection threading.Lock,
            # so we just verify the context manager works without error.
            with write_lock("test_wl.sqlite"):
                pass
        else:
            lock = _db_write_locks["test_wl.sqlite"]
            assert not lock.locked()
            with write_lock("test_wl.sqlite"):
                assert lock.locked()
            assert not lock.locked()

    def test_write_lock_nonexistent_db(self):
        """write_lock for non-existent DB should not crash."""
        # Should not raise even if no connection/lock exists
        with write_lock("nonexistent.sqlite"):
            pass

    def test_write_lock_mutual_exclusion(self):
        """Only one thread should hold write lock at a time."""
        get_connection("test_thread_wl.sqlite")
        results = []
        lock_held = threading.Event()

        def writer(thread_id):
            with write_lock("test_thread_wl.sqlite"):
                results.append(f"start_{thread_id}")
                # Hold the lock briefly
                import time
                time.sleep(0.05)
                results.append(f"end_{thread_id}")

        t1 = threading.Thread(target=writer, args=(1,))
        t2 = threading.Thread(target=writer, args=(2,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # Both threads should have completed
        assert len(results) == 4
        # Find start positions and check their ends follow immediately
        for i in range(len(results)):
            if results[i].startswith("start"):
                thread_id = results[i].split("_")[1]
                # The next entry should be the corresponding end
                assert results[i + 1] == f"end_{thread_id}"


# ============================================================
#  PRAGMA OPTIMIZATION TESTS
# ============================================================

class TestPragmaOptimization:
    """Tests for _optimize_pragma function."""

    def test_wal_mode_set(self):
        """Connection should have WAL journal mode."""
        conn = get_connection("test_pragma.sqlite")
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0].lower() == "wal"

    def test_busy_timeout_set(self):
        """Connection should have busy timeout set."""
        conn = get_connection("test_pragma2.sqlite")
        result = conn.execute("PRAGMA busy_timeout").fetchone()
        assert result[0] == 5000

    def test_synchronous_mode(self):
        """Connection should have synchronous=NORMAL."""
        conn = get_connection("test_pragma3.sqlite")
        result = conn.execute("PRAGMA synchronous").fetchone()
        # NORMAL = 1
        assert result[0] == 1


# ============================================================
#  INITIALIZE DATABASES TESTS
# ============================================================

class TestInitializeDatabases:
    """Tests for initialize_databases function."""

    def test_creates_all_databases(self):
        """initialize_databases should create all required databases."""
        initialize_databases()

        data_dir = db_initializer_mod.get_data_dir()
        expected_dbs = [
            "graph_ast.sqlite",
            "theorem_cache.sqlite",
            "merkle_ledger.sqlite",
            "request_log.sqlite",
        ]
        for db_name in expected_dbs:
            db_path = data_dir / db_name
            assert db_path.exists(), f"Database {db_name} was not created"

    def test_ast_nodes_table_exists(self):
        """graph_ast.sqlite should have ast_nodes table."""
        initialize_databases()
        conn = get_connection("graph_ast.sqlite")
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ast_nodes'"
        ).fetchone()
        assert result is not None

    def test_theorems_table_exists(self):
        """theorem_cache.sqlite should have theorems table."""
        initialize_databases()
        conn = get_connection("theorem_cache.sqlite")
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='theorems'"
        ).fetchone()
        assert result is not None

    def test_ledger_table_exists(self):
        """merkle_ledger.sqlite should have ledger table."""
        initialize_databases()
        conn = get_connection("merkle_ledger.sqlite")
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ledger'"
        ).fetchone()
        assert result is not None

    def test_requests_table_exists(self):
        """request_log.sqlite should have requests table."""
        initialize_databases()
        conn = get_connection("request_log.sqlite")
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='requests'"
        ).fetchone()
        assert result is not None

    def test_ast_nodes_indexes_created(self):
        """graph_ast.sqlite should have indexes on ast_nodes."""
        initialize_databases()
        conn = get_connection("graph_ast.sqlite")
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='ast_nodes'"
        ).fetchall()
        idx_names = [row[0] for row in indexes]
        assert "idx_ast_name" in idx_names
        assert "idx_ast_type" in idx_names

    def test_idempotent_initialization(self):
        """Calling initialize_databases twice should not raise errors."""
        initialize_databases()
        initialize_databases()  # Should be idempotent
        # Verify database is still functional
        conn = get_connection("graph_ast.sqlite")
        conn.execute("SELECT COUNT(*) FROM ast_nodes")
