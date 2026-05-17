"""
ZENIC-AGENTS - PostgreSQL Schema DDL & Connection Management

Schema definitions and connection helpers for PgBackend.
Auto-creates tables on connect() if they don't exist.
"""

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zenic_agents.distributed.pg_backend")


# ============================================================
#  SCHEMA DDL
# ============================================================

_SCHEMA_SQL = """
-- ZENIC Coordination Schema (auto-created on connect)
-- All tables use IF NOT EXISTS for safe re-runs

CREATE TABLE IF NOT EXISTS coord_tasks (
    task_id         TEXT PRIMARY KEY,
    queue_name      TEXT NOT NULL,
    task_type       TEXT NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}',
    priority        INTEGER NOT NULL DEFAULT 0,
    delay_until     DOUBLE PRECISION,
    tenant_id       TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    worker_id       TEXT,
    lease_expires_at DOUBLE PRECISION,
    created_at      DOUBLE PRECISION NOT NULL,
    completed_at    DOUBLE PRECISION,
    result          JSONB,
    error           TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    max_retries     INTEGER NOT NULL DEFAULT 3
);

CREATE INDEX IF NOT EXISTS idx_coord_tasks_queue_status
    ON coord_tasks (queue_name, status, priority DESC, created_at);

CREATE INDEX IF NOT EXISTS idx_coord_tasks_lease
    ON coord_tasks (queue_name, lease_expires_at)
    WHERE status = 'running';

CREATE INDEX IF NOT EXISTS idx_coord_tasks_tenant
    ON coord_tasks (tenant_id, status)
    WHERE tenant_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS coord_locks (
    lock_name       TEXT PRIMARY KEY,
    holder_id       TEXT NOT NULL,
    expires_at      DOUBLE PRECISION NOT NULL,
    acquired_at     DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS coord_elections (
    election_name   TEXT PRIMARY KEY,
    leader_id       TEXT NOT NULL,
    expires_at      DOUBLE PRECISION NOT NULL,
    acquired_at     DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS coord_circuits (
    circuit_name    TEXT PRIMARY KEY,
    state_data      JSONB NOT NULL DEFAULT '{}',
    version         INTEGER NOT NULL DEFAULT 1,
    updated_at      DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS coord_sagas (
    saga_id         TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'PENDING',
    context_data    JSONB NOT NULL DEFAULT '{}',
    error           TEXT,
    created_at      DOUBLE PRECISION NOT NULL,
    updated_at      DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS coord_saga_steps (
    saga_id         TEXT NOT NULL REFERENCES coord_sagas(saga_id) ON DELETE CASCADE,
    step_name       TEXT NOT NULL,
    step_order      INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'PENDING',
    result          JSONB,
    error           TEXT,
    timeout_seconds DOUBLE PRECISION,
    updated_at      DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (saga_id, step_name)
);

CREATE TABLE IF NOT EXISTS coord_nodes (
    node_id         TEXT PRIMARY KEY,
    hostname        TEXT,
    ip_address      TEXT,
    capabilities    JSONB NOT NULL DEFAULT '{}',
    status          JSONB NOT NULL DEFAULT '{}',
    registered_at   DOUBLE PRECISION NOT NULL,
    last_heartbeat  DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_coord_nodes_heartbeat
    ON coord_nodes (last_heartbeat);
"""


# ============================================================
#  CONNECTION MANAGEMENT MIXIN
# ============================================================

class PgConnectionMixin:
    """
    Mixin providing PostgreSQL connection management and DB helpers.

    Provides:
    - connect() / disconnect() / health_check()
    - _get_conn() / _put_conn()
    - _execute_ddl() / _execute_query() / _execute_modify()
    """

    async def connect(self) -> None:
        """Initialize PostgreSQL connection and create schema."""
        try:
            import psycopg2  # type: ignore[import-unresolved]
            from psycopg2 import pool
        except ImportError:
            raise ImportError(
                "psycopg2 is required for PostgreSQL coordination backend. "
                "Install with: pip install psycopg2-binary"
            )

        conn_string = self._config.connection_string
        if not conn_string:
            # Try environment variable
            import os
            conn_string = os.environ.get(
                "DATABASE_URL_SYNC",
                os.environ.get("DATABASE_URL", ""),
            )
            # Convert asyncpg URL to psycopg2 URL
            if conn_string.startswith("postgresql+asyncpg://"):
                conn_string = conn_string.replace("postgresql+asyncpg://", "postgresql://")
            elif conn_string.startswith("postgresql+psycopg2://"):
                conn_string = conn_string.replace("postgresql+psycopg2://", "postgresql://")

        if not conn_string:
            raise ValueError(
                "No PostgreSQL connection string provided. Set "
                "BackendConfig.connection_string or DATABASE_URL_SYNC env var."
            )

        try:
            self._pool = pool.ThreadedConnectionPool(
                minconn=self._config.pool_min,
                maxconn=self._config.pool_max,
                dsn=conn_string,
                connect_timeout=int(self._config.connect_timeout),
            )
        except Exception:
            # Fallback to single connection
            logger.warning(
                "PgBackend: Connection pool creation failed, "
                "falling back to single connection"
            )
            self._pool = None
            self._conn = psycopg2.connect(conn_string)
            self._conn.autocommit = True

        # Create schema
        self._execute_ddl(_SCHEMA_SQL)

        self._connected = True
        logger.info(
            "PgBackend: Connected (node_id=%s, pool=%s)",
            self._node_id,
            "yes" if self._pool else "single",
        )

    async def disconnect(self) -> None:
        """Close all connections."""
        if self._pool is not None:
            self._pool.closeall()
            self._pool = None
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        self._connected = False
        logger.info("PgBackend: Disconnected")

    async def health_check(self) -> Dict[str, Any]:
        """Check PostgreSQL health with a simple query."""
        try:
            start = time.monotonic()
            row = self._execute_query("SELECT 1 AS ok")
            latency_ms = (time.monotonic() - start) * 1000
            healthy = row and row[0].get("ok") == 1
        except Exception as exc:
            latency_ms = -1.0
            healthy = False
            logger.error("PgBackend health check failed: %s", exc)

        return {
            "healthy": healthy,
            "backend_type": "postgresql",
            "latency_ms": latency_ms,
            "node_id": self._node_id,
        }

    # ----------------------------------------------------------
    #  INTERNAL DB HELPERS
    # ----------------------------------------------------------

    def _get_conn(self) -> Any:
        """Get a connection from pool or fallback."""
        if self._pool is not None:
            return self._pool.getconn()
        return self._conn

    def _put_conn(self, conn: Any) -> None:
        """Return connection to pool."""
        if self._pool is not None and conn is not None:
            self._pool.putconn(conn)

    def _execute_ddl(self, sql: str) -> None:
        """Execute DDL statements (auto-commit)."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)  # nosemgrep: sqlalchemy-execute-raw-query
            if not conn.autocommit:
                conn.commit()
        except Exception as exc:
            logger.error("PgBackend DDL error: %s", exc)
            if not conn.autocommit:
                conn.rollback()
            raise
        finally:
            self._put_conn(conn)

    def _execute_query(
        self,
        sql: str,
        params: Optional[tuple] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a query and return results as list of dicts."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)  # nosemgrep: sqlalchemy-execute-raw-query
                if cur.description is None:
                    return []
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                return [dict(zip(columns, row)) for row in rows]
        except Exception:
            if not conn.autocommit:
                conn.rollback()
            raise
        finally:
            self._put_conn(conn)

    def _execute_modify(
        self,
        sql: str,
        params: Optional[tuple] = None,
    ) -> int:
        """Execute INSERT/UPDATE/DELETE, return affected row count."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)  # nosemgrep: sqlalchemy-execute-raw-query
                affected = cur.rowcount
            if not conn.autocommit:
                conn.commit()
            return affected
        except Exception:
            if not conn.autocommit:
                conn.rollback()
            raise
        finally:
            self._put_conn(conn)
