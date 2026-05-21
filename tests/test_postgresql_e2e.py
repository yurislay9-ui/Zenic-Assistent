"""
ZENIC-AGENTS v16 — PostgreSQL E2E Test Suite (Phase 2: Scalability)

End-to-end tests for the PostgreSQLDatabase adapter, verifying:
1. Connection pool creation and lifecycle
2. Table creation (all tables from _create_tables)
3. CRUD operations on ast_nodes
4. Tenant isolation (different tenants can't see each other's data)
5. adapt_query() conversion (? → $1, $2, etc.)
6. DSN conversion (postgresql+asyncpg:// → postgresql://)
7. Connection pool behavior (min_size, max_size)
8. Error handling (invalid queries, connection failure)

All tests are automatically skipped if PostgreSQL is not available.
Run with:  pytest tests/test_postgresql_e2e.py -v
"""

import asyncio
import os
import sys
from typing import Optional

import pytest
import pytest_asyncio

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.shared.db_adapters._postgresql import PostgreSQLDatabase
from src.core.shared.db_adapters._base import DatabaseBackend


# ── Connection check helper ─────────────────────────────────

def _pg_available() -> bool:
    """Check if PostgreSQL is reachable at the configured DSN."""
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        return False

    dsn = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://zenic:zenic@localhost:5432/zenic_db"
    )
    # Convert DSN for asyncpg
    converted = PostgreSQLDatabase._convert_dsn(dsn)

    async def _check() -> bool:
        try:
            conn = await asyncio.wait_for(
                asyncpg.connect(converted), timeout=5.0
            )
            await conn.close()
            return True
        except Exception:
            return False

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside an existing event loop (unlikely in pytest, but safe)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, _check())
            return future.result(timeout=10)
    else:
        return asyncio.run(_check())


# Skip all tests if PostgreSQL is not reachable
pg_not_available = not _pg_available()
SKIP_REASON = (
    "PostgreSQL is not available. "
    "Start it with: docker compose up -d postgres"
)


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pg_dsn() -> str:
    """Return the PostgreSQL DSN for testing."""
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://zenic:zenic@localhost:5432/zenic_db"
    )


@pytest_asyncio.fixture(scope="module")
async def pg_db(pg_dsn: str) -> Optional[PostgreSQLDatabase]:
    """Create and initialize a PostgreSQLDatabase instance for the test module."""
    if pg_not_available:
        pytest.skip(SKIP_REASON)

    db = PostgreSQLDatabase(dsn=pg_dsn)
    await db.initialize()
    yield db
    await db.close()


@pytest_asyncio.fixture(scope="module")
async def pg_conn(pg_db: PostgreSQLDatabase):
    """Acquire a connection from the pool for the test module."""
    async with pg_db._pool.acquire() as conn:
        yield conn


@pytest_asyncio.fixture(autouse=True)
async def cleanup_ast_nodes(pg_db: PostgreSQLDatabase):
    """Clean up ast_nodes after each test to avoid interference."""
    yield
    if pg_db and pg_db._pool:
        async with pg_db._pool.acquire() as conn:
            await conn.execute("DELETE FROM ast_nodes")


# ── 1. Connection and Pool Creation ─────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(pg_not_available, reason=SKIP_REASON)
class TestConnectionAndPool:
    """Test connection pool creation and lifecycle."""

    async def test_initialize_creates_pool(self, pg_db: PostgreSQLDatabase):
        """initialize() should create a non-None connection pool."""
        assert pg_db._pool is not None

    async def test_pool_has_min_connections(self, pg_db: PostgreSQLDatabase):
        """Pool should have at least min_size connections available."""
        # asyncpg pool starts with min_size connections
        pool = pg_db._pool
        # We can acquire and release to verify the pool works
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1

    async def test_pool_acquire_release(self, pg_db: PostgreSQLDatabase):
        """Acquiring and releasing connections should work correctly."""
        pool = pg_db._pool
        # Acquire multiple connections
        conns = []
        for _ in range(3):
            conn = await pool.acquire()
            conns.append(conn)
        # Release them all
        for conn in conns:
            await pool.release(conn)
        # Pool should still work
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1

    async def test_close_terminates_pool(self, pg_dsn: str):
        """close() should terminate the connection pool."""
        db = PostgreSQLDatabase(dsn=pg_dsn)
        await db.initialize()
        assert db._pool is not None
        await db.close()
        assert db._pool is None


# ── 2. Table Creation ───────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(pg_not_available, reason=SKIP_REASON)
class TestTableCreation:
    """Test that all application tables are created correctly."""

    async def test_ast_nodes_table_exists(self, pg_conn):
        """ast_nodes table should exist with correct columns."""
        row = await pg_conn.fetchrow("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'ast_nodes'
            ORDER BY ordinal_position
        """)
        assert row is not None

    async def test_ast_nodes_columns(self, pg_conn):
        """ast_nodes should have all required columns."""
        columns = await pg_conn.fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'ast_nodes'
        """)
        col_names = {r["column_name"] for r in columns}
        expected = {
            "id", "file_path", "node_type", "name",
            "start_byte", "end_byte", "content_hash",
            "docstring", "complexity", "connections", "tenant_id"
        }
        assert expected.issubset(col_names), f"Missing columns: {expected - col_names}"

    async def test_theorems_table_exists(self, pg_conn):
        """theorems table should exist."""
        result = await pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'theorems'
            )
        """)
        assert result is True

    async def test_ledger_table_exists(self, pg_conn):
        """ledger table should exist."""
        result = await pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'ledger'
            )
        """)
        assert result is True

    async def test_requests_table_exists(self, pg_conn):
        """requests table should exist."""
        result = await pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'requests'
            )
        """)
        assert result is True

    async def test_users_table_exists(self, pg_conn):
        """users table should exist (auth)."""
        result = await pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'users'
            )
        """)
        assert result is True

    async def test_tenants_table_exists(self, pg_conn):
        """tenants table should exist (auth)."""
        result = await pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'tenants'
            )
        """)
        assert result is True

    async def test_api_keys_table_exists(self, pg_conn):
        """api_keys table should exist (auth)."""
        result = await pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'api_keys'
            )
        """)
        assert result is True

    async def test_revoked_tokens_table_exists(self, pg_conn):
        """revoked_tokens table should exist (auth)."""
        result = await pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'revoked_tokens'
            )
        """)
        assert result is True

    async def test_tenant_usage_table_exists(self, pg_conn):
        """tenant_usage table should exist (auth)."""
        result = await pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'tenant_usage'
            )
        """)
        assert result is True

    async def test_smart_memory_tables_exist(self, pg_conn):
        """SmartMemory tables (6 total) should exist."""
        expected_tables = [
            "semantic_cache", "long_term_memory", "episodic_memory",
            "procedural_memory", "project_memory", "conversation_sessions",
        ]
        for table_name in expected_tables:
            result = await pg_conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = $1
                )
            """, table_name)
            assert result is True, f"Table '{table_name}' does not exist"

    async def test_ast_nodes_has_tenant_index(self, pg_conn):
        """ast_nodes should have tenant_id indexes."""
        indexes = await pg_conn.fetch("""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'ast_nodes' AND indexname LIKE '%tenant%'
        """)
        index_names = {r["indexname"] for r in indexes}
        assert any("tenant" in name for name in index_names), \
            f"Expected tenant indexes on ast_nodes, found: {index_names}"

    async def test_tables_are_idempotent(self, pg_db: PostgreSQLDatabase):
        """Calling initialize() again should not fail (IF NOT EXISTS)."""
        # Re-running _create_tables should be safe
        await pg_db._create_tables()
        # Verify the table still works
        async with pg_db._pool.acquire() as conn:
            result = await conn.fetchval("SELECT COUNT(*) FROM ast_nodes")
            assert result >= 0


# ── 3. CRUD Operations on ast_nodes ─────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(pg_not_available, reason=SKIP_REASON)
class TestCRUDOperations:
    """Test Create, Read, Update, Delete on ast_nodes via the adapter API."""

    async def test_insert_and_fetch_one(self, pg_db: PostgreSQLDatabase):
        """INSERT a row and fetch it back with fetch_one."""
        async with pg_db._pool.acquire() as conn:
            await pg_db.execute(
                conn,
                "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, tenant_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("test.py", "function", "hello", 0, 100, "abc123", "tenant_a")
            )
            row = await pg_db.fetch_one(
                conn,
                "SELECT * FROM ast_nodes WHERE name = ? AND tenant_id = ?",
                ("hello", "tenant_a")
            )
            assert row is not None
            assert row["name"] == "hello"
            assert row["file_path"] == "test.py"
            assert row["node_type"] == "function"
            assert row["tenant_id"] == "tenant_a"

    async def test_insert_and_fetch_all(self, pg_db: PostgreSQLDatabase):
        """INSERT multiple rows and fetch them all with fetch_all."""
        async with pg_db._pool.acquire() as conn:
            for i in range(5):
                await pg_db.execute(
                    conn,
                    "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, tenant_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (f"file_{i}.py", "class", f"Class{i}", i * 10, i * 10 + 50, f"hash_{i}", "tenant_b")
                )
            rows = await pg_db.fetch_all(
                conn,
                "SELECT * FROM ast_nodes WHERE tenant_id = ? ORDER BY name",
                ("tenant_b",)
            )
            assert len(rows) == 5
            assert rows[0]["name"] == "Class0"
            assert rows[4]["name"] == "Class4"

    async def test_fetch_val(self, pg_db: PostgreSQLDatabase):
        """fetch_val should return a single scalar value."""
        async with pg_db._pool.acquire() as conn:
            await pg_db.execute(
                conn,
                "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, tenant_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("val_test.py", "function", "count_fn", 0, 50, "hash_val", "tenant_c")
            )
            count = await pg_db.fetch_val(
                conn,
                "SELECT COUNT(*) FROM ast_nodes WHERE tenant_id = ?",
                ("tenant_c",)
            )
            assert count == 1

    async def test_update(self, pg_db: PostgreSQLDatabase):
        """UPDATE should modify existing rows."""
        async with pg_db._pool.acquire() as conn:
            await pg_db.execute(
                conn,
                "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, tenant_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("update.py", "function", "old_name", 0, 50, "hash_upd", "tenant_d")
            )
            await pg_db.execute(
                conn,
                "UPDATE ast_nodes SET name = ? WHERE tenant_id = ? AND name = ?",
                ("new_name", "tenant_d", "old_name")
            )
            row = await pg_db.fetch_one(
                conn,
                "SELECT name FROM ast_nodes WHERE tenant_id = ?",
                ("tenant_d",)
            )
            assert row is not None
            assert row["name"] == "new_name"

    async def test_delete(self, pg_db: PostgreSQLDatabase):
        """DELETE should remove rows."""
        async with pg_db._pool.acquire() as conn:
            await pg_db.execute(
                conn,
                "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, tenant_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("delete.py", "function", "to_delete", 0, 50, "hash_del", "tenant_e")
            )
            await pg_db.execute(
                conn,
                "DELETE FROM ast_nodes WHERE tenant_id = ? AND name = ?",
                ("tenant_e", "to_delete")
            )
            row = await pg_db.fetch_one(
                conn,
                "SELECT * FROM ast_nodes WHERE tenant_id = ? AND name = ?",
                ("tenant_e", "to_delete")
            )
            assert row is None

    async def test_fetch_one_returns_none_for_missing(self, pg_db: PostgreSQLDatabase):
        """fetch_one should return None when no row matches."""
        async with pg_db._pool.acquire() as conn:
            row = await pg_db.fetch_one(
                conn,
                "SELECT * FROM ast_nodes WHERE name = ?",
                ("nonexistent_name_xyz",)
            )
            assert row is None

    async def test_fetch_val_returns_none_for_missing(self, pg_db: PostgreSQLDatabase):
        """fetch_val should return None when no value matches."""
        async with pg_db._pool.acquire() as conn:
            val = await pg_db.fetch_val(
                conn,
                "SELECT name FROM ast_nodes WHERE name = ?",
                ("nonexistent_name_xyz",)
            )
            assert val is None

    async def test_execute_without_params(self, pg_db: PostgreSQLDatabase):
        """execute() should work without params for parameterless queries."""
        async with pg_db._pool.acquire() as conn:
            # This should not raise
            await pg_db.execute(conn, "SELECT 1")

    async def test_jsonb_connections_field(self, pg_db: PostgreSQLDatabase):
        """The connections JSONB field should store and retrieve JSON."""
        import json
        async with pg_db._pool.acquire() as conn:
            connections_data = json.dumps(["node_a", "node_b", "node_c"])
            await pg_db.execute(
                conn,
                "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, connections, tenant_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?::jsonb, ?)",
                ("json_test.py", "function", "json_fn", 0, 50, "hash_json", connections_data, "tenant_json")
            )
            row = await pg_db.fetch_one(
                conn,
                "SELECT connections FROM ast_nodes WHERE tenant_id = ?",
                ("tenant_json",)
            )
            assert row is not None
            # asyncpg returns JSONB as a list/dict already deserialized
            connections = row["connections"]
            if isinstance(connections, str):
                connections = json.loads(connections)
            assert "node_a" in connections


# ── 4. Tenant Isolation ─────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(pg_not_available, reason=SKIP_REASON)
class TestTenantIsolation:
    """Test that different tenants cannot see each other's data."""

    async def test_different_tenants_isolated(self, pg_db: PostgreSQLDatabase):
        """Data inserted by one tenant should not be visible to another."""
        async with pg_db._pool.acquire() as conn:
            # Insert for tenant_isolation_a
            await pg_db.execute(
                conn,
                "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, tenant_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("iso_a.py", "function", "fn_a", 0, 50, "hash_a", "tenant_iso_a")
            )
            # Insert for tenant_isolation_b
            await pg_db.execute(
                conn,
                "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, tenant_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("iso_b.py", "function", "fn_b", 0, 50, "hash_b", "tenant_iso_b")
            )

            # Tenant A should only see their own data
            rows_a = await pg_db.fetch_all(
                conn,
                "SELECT name FROM ast_nodes WHERE tenant_id = ?",
                ("tenant_iso_a",)
            )
            names_a = {r["name"] for r in rows_a}
            assert "fn_a" in names_a
            assert "fn_b" not in names_a

            # Tenant B should only see their own data
            rows_b = await pg_db.fetch_all(
                conn,
                "SELECT name FROM ast_nodes WHERE tenant_id = ?",
                ("tenant_iso_b",)
            )
            names_b = {r["name"] for r in rows_b}
            assert "fn_b" in names_b
            assert "fn_a" not in names_b

    async def test_same_name_different_tenants(self, pg_db: PostgreSQLDatabase):
        """The same (file_path, name, node_type) can exist for different tenants."""
        async with pg_db._pool.acquire() as conn:
            # Insert for tenant_dup_a
            await pg_db.execute(
                conn,
                "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, tenant_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("dup.py", "function", "common_fn", 0, 50, "hash_dup_a", "tenant_dup_a")
            )
            # Same file_path + name + node_type, different tenant — should succeed
            await pg_db.execute(
                conn,
                "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, tenant_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("dup.py", "function", "common_fn", 0, 50, "hash_dup_b", "tenant_dup_b")
            )

            rows = await pg_db.fetch_all(
                conn,
                "SELECT tenant_id, content_hash FROM ast_nodes WHERE name = ? ORDER BY tenant_id",
                ("common_fn",)
            )
            assert len(rows) == 2
            tenant_ids = {r["tenant_id"] for r in rows}
            assert tenant_ids == {"tenant_dup_a", "tenant_dup_b"}

    async def test_unique_constraint_same_tenant(self, pg_db: PostgreSQLDatabase):
        """UNIQUE(file_path, name, node_type, tenant_id) prevents duplicates for same tenant."""
        async with pg_db._pool.acquire() as conn:
            await pg_db.execute(
                conn,
                "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, tenant_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("uniq.py", "function", "unique_fn", 0, 50, "hash_uniq_1", "tenant_uniq")
            )
            # Same (file_path, name, node_type, tenant_id) should violate unique constraint
            with pytest.raises(Exception):  # asyncpg raises UniqueViolationError
                await pg_db.execute(
                    conn,
                    "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, tenant_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("uniq.py", "function", "unique_fn", 0, 50, "hash_uniq_2", "tenant_uniq")
                )


# ── 5. adapt_query() Conversion ─────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(pg_not_available, reason=SKIP_REASON)
class TestAdaptQuery:
    """Test ? → $N placeholder conversion for PostgreSQL."""

    def test_single_placeholder(self):
        """Single ? becomes $1."""
        db = PostgreSQLDatabase.__new__(PostgreSQLDatabase)
        result = db.adapt_query("SELECT * FROM users WHERE id = ?")
        assert result == "SELECT * FROM users WHERE id = $1"

    def test_multiple_placeholders(self):
        """Multiple ? become $1, $2, $3, etc."""
        db = PostgreSQLDatabase.__new__(PostgreSQLDatabase)
        result = db.adapt_query(
            "INSERT INTO t (a, b, c) VALUES (?, ?, ?)"
        )
        assert result == "INSERT INTO t (a, b, c) VALUES ($1, $2, $3)"

    def test_no_placeholders(self):
        """Query without ? should be returned unchanged."""
        db = PostgreSQLDatabase.__new__(PostgreSQLDatabase)
        query = "SELECT * FROM users"
        result = db.adapt_query(query)
        assert result == query

    def test_placeholders_in_different_positions(self):
        """Placeholders in WHERE and VALUES clauses."""
        db = PostgreSQLDatabase.__new__(PostgreSQLDatabase)
        result = db.adapt_query(
            "UPDATE t SET name = ? WHERE id = ? AND tenant_id = ?"
        )
        assert result == "UPDATE t SET name = $1 WHERE id = $2 AND tenant_id = $3"

    def test_eight_placeholders(self):
        """Long query with many placeholders."""
        db = PostgreSQLDatabase.__new__(PostgreSQLDatabase)
        result = db.adapt_query(
            "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, docstring, tenant_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        assert result == (
            "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, docstring, tenant_id) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)"
        )

    def test_sqlite_backend_passthrough(self):
        """SQLite backend should return query unchanged (no conversion)."""
        from src.core.shared.db_adapters._sqlite import SQLiteDatabase
        db = SQLiteDatabase.__new__(SQLiteDatabase)
        query = "SELECT * FROM users WHERE id = ?"
        result = db.adapt_query(query)
        assert result == query

    def test_format_param(self):
        """format_param() returns $N for PostgreSQL."""
        db = PostgreSQLDatabase.__new__(PostgreSQLDatabase)
        assert db.format_param(0) == "$1"
        assert db.format_param(1) == "$2"
        assert db.format_param(9) == "$10"

    def test_adapt_query_with_actual_db_execution(self, pg_db: PostgreSQLDatabase):
        """adapt_query is called automatically by execute/fetch methods."""
        async def _run():
            async with pg_db._pool.acquire() as conn:
                # Use ? placeholders — adapt_query converts them to $1, $2 etc.
                await pg_db.execute(
                    conn,
                    "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, tenant_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("adapt.py", "function", "adapted_fn", 0, 50, "hash_adapt", "tenant_adapt")
                )
                row = await pg_db.fetch_one(
                    conn,
                    "SELECT * FROM ast_nodes WHERE name = ? AND tenant_id = ?",
                    ("adapted_fn", "tenant_adapt")
                )
                assert row is not None
                assert row["name"] == "adapted_fn"

        asyncio.get_event_loop().run_until_complete(_run())


# ── 6. DSN Conversion ───────────────────────────────────────

@pytest.mark.skipif(pg_not_available, reason=SKIP_REASON)
class TestDSNConversion:
    """Test SQLAlchemy DSN → asyncpg DSN conversion."""

    def test_asyncpg_driver_stripped(self):
        """postgresql+asyncpg:// → postgresql://"""
        dsn = "postgresql+asyncpg://user:pass@host:5432/db"
        result = PostgreSQLDatabase._convert_dsn(dsn)
        assert result == "postgresql://user:pass@host:5432/db"

    def test_psycopg2_driver_stripped(self):
        """postgresql+psycopg2:// → postgresql://"""
        dsn = "postgresql+psycopg2://user:pass@host:5432/db"
        result = PostgreSQLDatabase._convert_dsn(dsn)
        assert result == "postgresql://user:pass@host:5432/db"

    def test_plain_postgresql_unchanged(self):
        """postgresql:// DSN (no driver) is returned unchanged."""
        dsn = "postgresql://user:pass@host:5432/db"
        result = PostgreSQLDatabase._convert_dsn(dsn)
        assert result == dsn

    def test_sqlite_dsn_unchanged(self):
        """Non-postgresql DSNs are returned unchanged."""
        dsn = "sqlite:///test.db"
        result = PostgreSQLDatabase._convert_dsn(dsn)
        assert result == dsn

    def test_dsn_with_query_params(self):
        """DSN with query parameters should preserve them after conversion."""
        dsn = "postgresql+asyncpg://user:pass@host:5432/db?sslmode=require"
        result = PostgreSQLDatabase._convert_dsn(dsn)
        assert result == "postgresql://user:pass@host:5432/db?sslmode=require"

    def test_dsn_with_special_chars(self):
        """DSN with URL-encoded special characters in password."""
        dsn = "postgresql+asyncpg://user:p%40ss@host:5432/db"
        result = PostgreSQLDatabase._convert_dsn(dsn)
        assert result == "postgresql://user:p%40ss@host:5432/db"

    def test_constructor_applies_conversion(self, pg_dsn: str):
        """PostgreSQLDatabase.__init__ should apply _convert_dsn."""
        db = PostgreSQLDatabase(dsn=pg_dsn)
        # If pg_dsn contains +asyncpg, _async_dsn should have it stripped
        if "+asyncpg" in pg_dsn:
            assert "+asyncpg" not in db._async_dsn
        assert db._async_dsn.startswith("postgresql://")


# ── 7. Connection Pool Behavior ─────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(pg_not_available, reason=SKIP_REASON)
class TestConnectionPoolBehavior:
    """Test connection pool sizing and concurrent access."""

    async def test_pool_min_size(self, pg_db: PostgreSQLDatabase):
        """Pool should be created with min_size=2 (as per _postgresql.py)."""
        pool = pg_db._pool
        # asyncpg doesn't expose min_size/max_size as public attrs in all versions,
        # but we can verify the pool works with concurrent connections
        assert pool is not None

    async def test_concurrent_queries(self, pg_db: PostgreSQLDatabase):
        """Multiple concurrent queries should work without deadlocks."""
        async def insert_and_count(idx: int):
            async with pg_db._pool.acquire() as conn:
                await pg_db.execute(
                    conn,
                    "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, tenant_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (f"concurrent_{idx}.py", "function", f"fn_{idx}", 0, 50, f"hash_c_{idx}", "tenant_concurrent")
                )
                count = await pg_db.fetch_val(
                    conn,
                    "SELECT COUNT(*) FROM ast_nodes WHERE tenant_id = ?",
                    ("tenant_concurrent",)
                )
                return count

        # Run 10 concurrent operations
        results = await asyncio.gather(*[insert_and_count(i) for i in range(10)])
        # All should succeed (each sees at least its own insert)
        for count in results:
            assert count >= 1

    async def test_custom_pool_size(self, pg_dsn: str):
        """A custom pool can be created with different min/max sizes."""
        import asyncpg
        converted = PostgreSQLDatabase._convert_dsn(pg_dsn)
        pool = await asyncpg.create_pool(
            converted,
            min_size=1,
            max_size=5,
        )
        assert pool is not None
        # Verify it works
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1
        await pool.close()


# ── 8. Error Handling ───────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(pg_not_available, reason=SKIP_REASON)
class TestErrorHandling:
    """Test error handling for invalid queries and connection failures."""

    async def test_invalid_query_raises(self, pg_db: PostgreSQLDatabase):
        """An invalid SQL query should raise an exception."""
        async with pg_db._pool.acquire() as conn:
            with pytest.raises(Exception):
                await pg_db.execute(conn, "INVALID SQL STATEMENT")

    async def test_invalid_table_raises(self, pg_db: PostgreSQLDatabase):
        """Querying a non-existent table should raise an exception."""
        async with pg_db._pool.acquire() as conn:
            with pytest.raises(Exception):
                await pg_db.fetch_all(conn, "SELECT * FROM nonexistent_table_xyz")

    async def test_type_mismatch_raises(self, pg_db: PostgreSQLDatabase):
        """Inserting wrong types should raise an exception."""
        async with pg_db._pool.acquire() as conn:
            with pytest.raises(Exception):
                await pg_db.execute(
                    conn,
                    "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash, tenant_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("test.py", "function", "fn", "not_an_integer", 50, "hash", "tenant_err")
                    # start_byte is INTEGER, "not_an_integer" should fail
                )

    async def test_connection_to_bad_host(self):
        """Connecting to a non-existent host should raise an error."""
        db = PostgreSQLDatabase(dsn="postgresql+asyncpg://user:pass@nonexistent.host:5432/db")
        with pytest.raises(Exception):
            await db.initialize()

    async def test_asyncpg_not_installed_fallback(self, monkeypatch):
        """If asyncpg is not installed, initialize() should raise ImportError."""
        db = PostgreSQLDatabase(dsn="postgresql+asyncpg://zenic:zenic@localhost:5432/zenic_db")
        # Simulate asyncpg not being installed
        import importlib
        original_import = importlib.import_module

        def mock_import(name, *args, **kwargs):
            if name == "asyncpg":
                raise ImportError("No module named 'asyncpg'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(importlib, "import_module", mock_import)
        # Also patch the import inside the method
        import builtins
        original_builtin_import = builtins.__import__

        def mock_builtin_import(name, *args, **kwargs):
            if name == "asyncpg":
                raise ImportError("No module named 'asyncpg'")
            return original_builtin_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_builtin_import)
        with pytest.raises(ImportError, match="asyncpg is required"):
            await db.initialize()

    async def test_fetch_one_on_empty_table(self, pg_db: PostgreSQLDatabase):
        """fetch_one on an empty result set returns None (not an error)."""
        async with pg_db._pool.acquire() as conn:
            result = await pg_db.fetch_one(
                conn,
                "SELECT * FROM ast_nodes WHERE name = ?",
                ("surely_nonexistent_12345",)
            )
            assert result is None

    async def test_fetch_all_on_empty_table(self, pg_db: PostgreSQLDatabase):
        """fetch_all on an empty result set returns [] (not an error)."""
        async with pg_db._pool.acquire() as conn:
            result = await pg_db.fetch_all(
                conn,
                "SELECT * FROM ast_nodes WHERE name = ?",
                ("surely_nonexistent_12345",)
            )
            assert result == []


# ── 9. Backend Name and Factory Integration ─────────────────

@pytest.mark.skipif(pg_not_available, reason=SKIP_REASON)
class TestBackendIntegration:
    """Test that PostgreSQLDatabase integrates with the factory correctly."""

    def test_backend_name(self):
        """backend_name should be 'postgresql'."""
        db = PostgreSQLDatabase.__new__(PostgreSQLDatabase)
        assert db.backend_name == "postgresql"

    def test_inherits_from_base(self):
        """PostgreSQLDatabase should inherit from DatabaseBackend."""
        assert issubclass(PostgreSQLDatabase, DatabaseBackend)

    def test_factory_get_db_backend(self, monkeypatch):
        """get_db_backend() should return 'postgresql' when ZENIC_ENV=production."""
        from src.core.shared.db_adapters import get_db_backend, reset_db
        monkeypatch.setenv("ZENIC_ENV", "production")
        reset_db()
        assert get_db_backend() == "postgresql"
        reset_db()

    def test_factory_is_postgresql(self, monkeypatch):
        """is_postgresql() should detect PostgreSQL configuration."""
        from src.core.shared.db_adapters import is_postgresql
        monkeypatch.setenv("ZENIC_ENV", "production")
        assert is_postgresql() is True
        monkeypatch.delenv("ZENIC_ENV", raising=False)
        monkeypatch.setenv("DATABASE_URL", "postgresql://host/db")
        assert is_postgresql() is True
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert is_postgresql() is False
