"""
Audit Logging — AuditLogger Class.

Centralized audit logging with dual output (structured logger + SQLite).
"""

import json
import logging
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from ._types import AuditEvent, AuditEventType, AuditSeverity

logger = logging.getLogger(__name__)


class AuditLogger:
    """Centralized audit logging with dual output.

    Writes audit events to:
    1. Structured logger (for log aggregation systems)
    2. SQLite database (for long-term retention and queries)

    The SQLite database is per-tenant capable, supporting
    GDPR right-to-erasure via tenant-scoped pruning.
    """

    def __init__(
        self,
        db_path: str = "audit_log.sqlite",
        retention_days: int = 90,
        max_events_per_query: int = 1000,
    ) -> None:
        self._db_path = db_path
        self._retention_days = retention_days
        self._max_events_per_query = max_events_per_query
        self._lock = threading.Lock()
        self._initialized = False
        self._audit_logger = logging.getLogger("zenic.audit")

        self._init_db()

    def _init_db(self) -> None:
        """Initialize the audit log SQLite database."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    trace_id TEXT,
                    span_id TEXT,
                    tenant_id TEXT NOT NULL,
                    user_id INTEGER,
                    ip_address TEXT,
                    description TEXT,
                    metadata TEXT,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_audit_tenant
                ON audit_events(tenant_id, timestamp DESC)
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_audit_type
                ON audit_events(event_type, timestamp DESC)
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_audit_trace
                ON audit_events(trace_id)
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_audit_created
                ON audit_events(created_at)
            """)
            conn.commit()
            conn.close()
            self._initialized = True
            logger.info("AuditLogger: Database initialized at %s", self._db_path)
        except Exception as exc:
            logger.error("AuditLogger: Database initialization failed: %s", exc)
            self._initialized = False

    def log(self, event: AuditEvent) -> None:
        """Record an audit event."""
        self._audit_logger.info(
            event.description or event.event_type.value,
            extra={
                "audit_event_id": event.event_id,
                "audit_event_type": event.event_type.value,
                "audit_severity": event.severity.value,
                "trace_id": event.trace_id,
                "span_id": event.span_id,
                "tenant_id": event.tenant_id,
                "user_id": event.user_id,
                "ip_address": event.ip_address,
                "audit_metadata": event.metadata,
            },
        )

        if self._initialized:
            self._persist_event(event)

    def log_event(
        self,
        event_type: AuditEventType,
        description: str,
        severity: AuditSeverity = AuditSeverity.INFO,
        tenant_id: str = "__anonymous__",
        user_id: Optional[int] = None,
        ip_address: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Convenience method: create and log an audit event."""
        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            tenant_id=tenant_id,
            user_id=user_id,
            ip_address=ip_address,
            description=description,
            metadata=metadata or {},
        )
        self.log(event)
        return event.event_id

    def _persist_event(self, event: AuditEvent) -> None:
        """Persist an event to the SQLite database."""
        try:
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT INTO audit_events
                       (event_id, event_type, severity, timestamp,
                        trace_id, span_id, tenant_id, user_id,
                        ip_address, description, metadata, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event.event_id,
                        event.event_type.value,
                        event.severity.value,
                        event.timestamp,
                        event.trace_id,
                        event.span_id,
                        event.tenant_id,
                        event.user_id,
                        event.ip_address,
                        event.description,
                        json.dumps(event.metadata, ensure_ascii=False, default=str),
                        time.time(),
                    ),
                )
                conn.commit()
                conn.close()
        except Exception as exc:
            logger.debug("AuditLogger: Persist failed: %s", exc)

    def query_events(
        self,
        tenant_id: Optional[str] = None,
        event_type: Optional[str] = None,
        user_id: Optional[int] = None,
        severity: Optional[str] = None,
        trace_id: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query audit events with filters."""
        if not self._initialized:
            return []

        conditions: List[str] = []
        params: List[Any] = []

        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if event_type is not None:
            conditions.append("event_type = ?")
            params.append(event_type)
        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)
        if severity is not None:
            conditions.append("severity = ?")
            params.append(severity)
        if trace_id is not None:
            conditions.append("trace_id = ?")
            params.append(trace_id)
        if since is not None:
            conditions.append("created_at >= ?")
            params.append(since)
        if until is not None:
            conditions.append("created_at <= ?")
            params.append(until)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        limit = min(limit, self._max_events_per_query)

        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                f"SELECT * FROM audit_events WHERE {where_clause} "
                f"ORDER BY created_at DESC LIMIT {limit}",
                params,
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error("AuditLogger: Query failed: %s", exc)
            return []

    def prune_old_events(self, days: Optional[int] = None) -> int:
        """Delete events older than the retention period."""
        retention = days or self._retention_days
        cutoff = time.time() - (retention * 86400)

        try:
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "DELETE FROM audit_events WHERE created_at < ?",
                    (cutoff,),
                )
                count = cursor.rowcount
                conn.commit()
                conn.close()
            if count > 0:
                logger.info("AuditLogger: Pruned %d events older than %d days", count, retention)
            return count
        except Exception as exc:
            logger.error("AuditLogger: Prune failed: %s", exc)
            return 0

    def purge_tenant_events(self, tenant_id: str) -> int:
        """Delete ALL audit events for a tenant (GDPR right to erasure)."""
        try:
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "DELETE FROM audit_events WHERE tenant_id = ?",
                    (tenant_id,),
                )
                count = cursor.rowcount
                conn.commit()
                conn.close()
            if count > 0:
                logger.info(
                    "AuditLogger: Purged %d events for tenant %s (GDPR)",
                    count, tenant_id[:8],
                )
            return count
        except Exception as exc:
            logger.error("AuditLogger: Tenant purge failed: %s", exc)
            return 0

    def get_event_count(self, tenant_id: Optional[str] = None) -> int:
        """Get total event count, optionally filtered by tenant."""
        if not self._initialized:
            return 0
        try:
            conn = sqlite3.connect(self._db_path)
            if tenant_id:
                row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT COUNT(*) FROM audit_events WHERE tenant_id = ?",
                    (tenant_id,),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()  # nosemgrep: sqlalchemy-execute-raw-query
            conn.close()
            return row[0] if row else 0
        except Exception:
            return 0
