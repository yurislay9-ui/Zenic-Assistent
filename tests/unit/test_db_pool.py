"""
Unit tests for SQLite Connection Pool

Tests for the connection pool, PRAGMA optimizations, and WAL mode.
"""

import pytest
import sqlite3
from src.core.shared.db_initializer import (
    get_connection, close_all_connections, initialize_databases,
)


class TestConnectionPool:
    """Tests for the SQLite connection pool."""

    def test_get_connection_returns_connection(self):
        """Should return a valid SQLite connection."""
        conn = get_connection("test_pool.sqlite")
        assert isinstance(conn, sqlite3.Connection)

    def test_get_connection_reuses_connection(self):
        """Should return the same connection for the same DB."""
        conn1 = get_connection("test_reuse.sqlite")
        conn2 = get_connection("test_reuse.sqlite")
        assert conn1 is conn2

    def test_get_connection_different_db(self):
        """Should return different connections for different DBs."""
        conn1 = get_connection("test_db1.sqlite")
        conn2 = get_connection("test_db2.sqlite")
        assert conn1 is not conn2

    def test_connection_has_wal_mode(self):
        """Connection should have WAL journal mode."""
        conn = get_connection("test_wal.sqlite")
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0].lower() == "wal"

    def test_connection_has_row_factory(self):
        """Connection should have Row factory set."""
        conn = get_connection("test_row_factory.sqlite")
        assert conn.row_factory is not None

    def test_initialize_databases_creates_tables(self):
        """initialize_databases should create all required tables."""
        initialize_databases()
        # Check graph_ast
        conn = get_connection("graph_ast.sqlite")
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "ast_nodes" in table_names

        # Check theorem_cache
        conn = get_connection("theorem_cache.sqlite")
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "theorems" in table_names

        # Check merkle_ledger
        conn = get_connection("merkle_ledger.sqlite")
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "ledger" in table_names

    def test_close_all_connections(self):
        """Should close all connections without error."""
        get_connection("test_close1.sqlite")
        get_connection("test_close2.sqlite")
        close_all_connections()
        # After closing, getting a new connection should work
        conn = get_connection("test_close1.sqlite")
        assert isinstance(conn, sqlite3.Connection)

    def test_broken_connection_recovery(self):
        """Should recover from broken connections."""
        conn = get_connection("test_broken.sqlite")
        conn.close()  # Force close
        # Getting the same DB should create a new connection
        conn2 = get_connection("test_broken.sqlite")
        assert isinstance(conn2, sqlite3.Connection)
        # Should be usable
        conn2.execute("SELECT 1")
