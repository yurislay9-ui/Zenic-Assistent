"""
Zenic-Agents Asistente - Approval Chain Persistence (Phase 6.1b)

Database operations for the ApprovalChain.
Separated from chain.py for the 400-line limit.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from ..chain import ApprovalRequest, ApprovalStatus, ApprovalPriority

logger = logging.getLogger(__name__)


class ApprovalChainDB:
    """Database operations for the ApprovalChain.

    Handles all SQLite persistence for approval requests:
    - Create schema
    - Persist new requests
    - Update existing requests
    - Query with filters
    - Row-to-object conversion
    """

    def __init__(self, db_path: str = "approval_chain.sqlite") -> None:
        self._db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the approval chain database."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS approval_requests (
                    request_id TEXT PRIMARY KEY,
                    action_type TEXT NOT NULL,
                    action_config TEXT NOT NULL,
                    required_role TEXT NOT NULL,
                    requested_by INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority TEXT NOT NULL DEFAULT 'normal',
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    approved_by INTEGER,
                    approved_at TEXT,
                    rejection_reason TEXT,
                    metadata TEXT DEFAULT '{}',
                    tenant_id TEXT DEFAULT '__anonymous__'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_approval_status
                ON approval_requests(status, created_at DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_approval_requested_by
                ON approval_requests(requested_by)
            """)
            conn.commit()
            conn.close()
            logger.info("ApprovalChainDB: Database initialized")
        except Exception as exc:
            logger.error("ApprovalChainDB: DB init failed: %s", exc)

    def persist_request(
        self, request: ApprovalRequest, tenant_id: str = "__anonymous__",
    ) -> None:
        """Persist a new request to the database."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT INTO approval_requests
                   (request_id, action_type, action_config, required_role,
                    requested_by, status, priority, created_at, expires_at,
                    approved_by, approved_at, rejection_reason, metadata, tenant_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    request.request_id, request.action_type,
                    json.dumps(request.action_config),
                    request.required_role, request.requested_by,
                    request.status.value, request.priority.value,
                    request.created_at, request.expires_at,
                    request.approved_by, request.approved_at,
                    request.rejection_reason,
                    json.dumps(request.metadata), tenant_id,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("ApprovalChainDB: Persist failed: %s", exc)

    def update_request(self, request: ApprovalRequest) -> None:
        """Update an existing request in the database."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """UPDATE approval_requests SET
                   status=?, required_role=?, expires_at=?,
                   approved_by=?, approved_at=?,
                   rejection_reason=?, metadata=?
                   WHERE request_id=?""",
                (
                    request.status.value, request.required_role,
                    request.expires_at, request.approved_by,
                    request.approved_at, request.rejection_reason,
                    json.dumps(request.metadata), request.request_id,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("ApprovalChainDB: Update failed: %s", exc)

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get a single request by ID."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM approval_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return self._row_to_request(row)
        except Exception as exc:
            logger.error("ApprovalChainDB: Get failed: %s", exc)
            return None

    def query_requests(
        self,
        status: Optional[ApprovalStatus] = None,
        required_role: Optional[str] = None,
        requested_by: Optional[int] = None,
        tenant_id: Optional[str] = None,
    ) -> List[ApprovalRequest]:
        """Query approval requests with optional filters."""
        conditions: List[str] = []
        params: List[Any] = []

        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)
        if required_role is not None:
            conditions.append("required_role = ?")
            params.append(required_role)
        if requested_by is not None:
            conditions.append("requested_by = ?")
            params.append(requested_by)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)

        where = " AND ".join(conditions) if conditions else "1=1"
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM approval_requests WHERE {where} ORDER BY created_at DESC",
                params,
            ).fetchall()
            conn.close()
            return [self._row_to_request(r) for r in rows]
        except Exception as exc:
            logger.error("ApprovalChainDB: Query failed: %s", exc)
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get approval chain statistics."""
        try:
            conn = sqlite3.connect(self._db_path)
            stats = {}
            for status in ApprovalStatus:
                row = conn.execute(
                    "SELECT COUNT(*) FROM approval_requests WHERE status = ?",
                    (status.value,),
                ).fetchone()
                stats[status.value] = row[0]
            conn.close()
            return stats
        except Exception:
            return {}

    @staticmethod
    def _row_to_request(row: sqlite3.Row) -> ApprovalRequest:
        """Convert a database row to an ApprovalRequest."""
        return ApprovalRequest(
            request_id=row["request_id"],
            action_type=row["action_type"],
            action_config=json.loads(row["action_config"]),
            required_role=row["required_role"],
            requested_by=row["requested_by"],
            status=ApprovalStatus(row["status"]),
            priority=ApprovalPriority(row["priority"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"] or "",
            approved_by=row["approved_by"],
            approved_at=row["approved_at"],
            rejection_reason=row["rejection_reason"] or "",
            metadata=json.loads(row["metadata"] or "{}"),
        )
