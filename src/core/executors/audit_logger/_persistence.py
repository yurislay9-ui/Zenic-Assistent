"""
ZENIC-AGENTS - Executor Audit Logger: SQLite Persistence

SQLite-based storage for audit entries with query and prune support.
"""

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from ._types import AuditEntry, AuditQuery

logger = logging.getLogger(__name__)


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS executor_audit (
    entry_id TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    operation TEXT NOT NULL DEFAULT '',
    executor_class TEXT NOT NULL DEFAULT '',
    verdict TEXT NOT NULL DEFAULT '',
    success INTEGER NOT NULL DEFAULT 0,
    duration_ms REAL NOT NULL DEFAULT 0.0,
    user_id TEXT NOT NULL DEFAULT '',
    tenant_id TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    request_id TEXT NOT NULL DEFAULT '',
    risk_score REAL NOT NULL DEFAULT 0.0,
    category TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}',
    merkle_hash TEXT NOT NULL DEFAULT '',
    prev_hash TEXT NOT NULL DEFAULT '',
    timestamp REAL NOT NULL DEFAULT 0.0
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_audit_action ON executor_audit(action_type);
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON executor_audit(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON executor_audit(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_user ON executor_audit(user_id);
"""


class AuditPersistence:
    """SQLite-based persistence for audit entries."""

    def __init__(self, db_path: str = "executor_audit.db") -> None:
        self._db_path = db_path
        self._initialized = False

    def _ensure_init(self) -> None:
        if self._initialized:
            return
        conn = sqlite3.connect(self._db_path)
        try:
            conn.executescript(_CREATE_TABLE_SQL + _CREATE_INDEX_SQL)
            conn.commit()
        finally:
            conn.close()
        self._initialized = True

    def save(self, entry: AuditEntry) -> None:
        """Persist an audit entry to SQLite."""
        self._ensure_init()
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT OR REPLACE INTO executor_audit
                   (entry_id, action_type, operation, executor_class, verdict,
                    success, duration_ms, user_id, tenant_id, session_id,
                    request_id, risk_score, category, error, metadata,
                    merkle_hash, prev_hash, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry.entry_id, entry.action_type, entry.operation,
                 entry.executor_class, entry.verdict,
                 int(entry.success), entry.duration_ms,
                 entry.user_id, entry.tenant_id, entry.session_id,
                 entry.request_id, entry.risk_score, entry.category,
                 entry.error, json.dumps(entry.metadata),
                 entry.merkle_hash, entry.prev_hash, entry.timestamp),
            )
            conn.commit()
        finally:
            conn.close()

    def query(self, q: AuditQuery) -> List[AuditEntry]:
        """Query audit entries with filters."""
        self._ensure_init()
        conditions: List[str] = []
        params: List[Any] = []

        if q.action_type:
            conditions.append("action_type = ?")
            params.append(q.action_type)
        if q.executor_class:
            conditions.append("executor_class = ?")
            params.append(q.executor_class)
        if q.user_id:
            conditions.append("user_id = ?")
            params.append(q.user_id)
        if q.tenant_id:
            conditions.append("tenant_id = ?")
            params.append(q.tenant_id)
        if q.success is not None:
            conditions.append("success = ?")
            params.append(int(q.success))
        if q.verdict:
            conditions.append("verdict = ?")
            params.append(q.verdict)
        if q.category:
            conditions.append("category = ?")
            params.append(q.category)
        if q.from_timestamp:
            conditions.append("timestamp >= ?")
            params.append(q.from_timestamp)
        if q.to_timestamp:
            conditions.append("timestamp <= ?")
            params.append(q.to_timestamp)

        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT * FROM executor_audit{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([q.limit, q.offset])

        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(sql, params).fetchall()  # nosemgrep: sqlalchemy-execute-raw-query
            return [self._row_to_entry(r) for r in rows]
        finally:
            conn.close()

    def prune(self, older_than_timestamp: float) -> int:
        """Delete audit entries older than given timestamp."""
        self._ensure_init()
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "DELETE FROM executor_audit WHERE timestamp < ?",
                (older_than_timestamp,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def _row_to_entry(self, row: sqlite3.Row) -> AuditEntry:
        """Convert a SQLite row to an AuditEntry."""
        return AuditEntry(
            entry_id=row["entry_id"],
            action_type=row["action_type"],
            operation=row["operation"],
            executor_class=row["executor_class"],
            verdict=row["verdict"],
            success=bool(row["success"]),
            duration_ms=row["duration_ms"],
            user_id=row["user_id"],
            tenant_id=row["tenant_id"],
            session_id=row["session_id"],
            request_id=row["request_id"],
            risk_score=row["risk_score"],
            category=row["category"],
            error=row["error"],
            metadata=json.loads(row["metadata"]),
            merkle_hash=row["merkle_hash"],
            prev_hash=row["prev_hash"],
            timestamp=row["timestamp"],
        )
