"""
Zenic-Agents Asistente - Batch Approval Engine (Phase C3)

Approve or reject multiple similar actions at once. A batch groups
identical-type approval requests so that an approver can act on all
of them in a single operation, with optional partial approval support.

Flow:
  1. create_batch() — validates configs, creates individual requests
     via ApprovalChain, stores batch metadata
  2. approve_batch() / reject_batch() — bulk approve/reject
  3. approve_partial() — approve only selected indices within the batch

Persistence: SQLite with retry logic.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1


@dataclass
class BatchRequest:
    """Metadata for a batch approval request."""

    batch_id: str = ""
    action_type: str = ""
    action_configs: List[Dict[str, Any]] = field(default_factory=list)
    requested_by: int = 0
    required_role: str = ""
    status: str = "pending"
    total_count: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    created_at: str = ""
    # Stores the individual request_ids created via ApprovalChain
    request_ids: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.batch_id:
            self.batch_id = f"bat-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if self.total_count == 0 and self.action_configs:
            self.total_count = len(self.action_configs)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "batch_id": self.batch_id,
            "action_type": self.action_type,
            "action_configs": self.action_configs,
            "requested_by": self.requested_by,
            "required_role": self.required_role,
            "status": self.status,
            "total_count": self.total_count,
            "approved_count": self.approved_count,
            "rejected_count": self.rejected_count,
            "created_at": self.created_at,
            "request_ids": self.request_ids,
        }


@dataclass
class BatchResult:
    """Result of a batch approve/reject operation."""

    batch_id: str = ""
    total: int = 0
    approved: int = 0
    rejected: int = 0
    errors: List[str] = field(default_factory=list)
    individual_results: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "batch_id": self.batch_id,
            "total": self.total,
            "approved": self.approved,
            "rejected": self.rejected,
            "errors": self.errors,
            "individual_results": self.individual_results,
        }


class BatchApprovalEngine:
    """Approve or reject multiple similar actions at once.

    Each batch creates individual ApprovalChain requests so that
    the existing audit trail and role checks are preserved.
    """

    def __init__(self, db_path: str = "batch_approval.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    # ── DB Initialisation ──────────────────────────────────

    def _init_db(self) -> None:
        """Create the batch_requests table if it does not exist."""
        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS batch_requests (
                    batch_id TEXT PRIMARY KEY,
                    action_type TEXT NOT NULL,
                    action_configs TEXT NOT NULL,
                    requested_by INTEGER NOT NULL,
                    required_role TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    total_count INTEGER NOT NULL DEFAULT 0,
                    approved_count INTEGER NOT NULL DEFAULT 0,
                    rejected_count INTEGER NOT NULL DEFAULT 0,
                    request_ids TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_batch_status
                ON batch_requests(status, created_at DESC)
            """)
            conn.commit()
            conn.close()

        self._with_retry(_do_init)

    # ── Core Operations ────────────────────────────────────

    def create_batch(
        self,
        action_type: str,
        action_configs: List[Dict[str, Any]],
        requested_by: int,
        required_role: str,
    ) -> BatchRequest:
        """Create a new batch of approval requests.

        Validates that all configs are for the same action_type,
        then creates individual approval requests via ApprovalChain.

        Args:
            action_type: The type of action for all configs in this batch.
            action_configs: List of action config dicts.
            requested_by: User ID requesting the batch.
            required_role: Minimum role required to approve.

        Returns:
            The created BatchRequest with populated request_ids.
        """
        if not action_configs:
            raise ValueError("Cannot create a batch with empty action_configs")

        # Validate all configs have the same action_type
        for i, cfg in enumerate(action_configs):
            cfg_action = cfg.get("action_type", "")
            if cfg_action and cfg_action != action_type:
                raise ValueError(
                    f"Config at index {i} has action_type '{cfg_action}' "
                    f"which does not match batch action_type '{action_type}'"
                )

        # Lazy import to avoid circular dependency
        from .chain import get_approval_chain

        chain = get_approval_chain()

        # Create individual approval requests
        request_ids: List[str] = []
        for cfg in action_configs:
            req = chain.create_request(
                action_type=action_type,
                action_config=cfg,
                requested_by=requested_by,
                required_role=required_role,
            )
            request_ids.append(req.request_id)

        batch = BatchRequest(
            action_type=action_type,
            action_configs=action_configs,
            requested_by=requested_by,
            required_role=required_role,
            status="pending",
            total_count=len(action_configs),
            request_ids=request_ids,
        )

        with self._lock:
            self._persist_batch(batch, insert=True)

        logger.info(
            "BatchApproval: Created batch %s — %d requests for '%s'",
            batch.batch_id, batch.total_count, action_type,
        )
        return batch

    def approve_batch(
        self,
        batch_id: str,
        approver_id: int,
        approver_role: str,
    ) -> BatchResult:
        """Approve ALL pending requests in the batch.

        Uses ApprovalChain.approve() for each individual request.
        Tracks successes and failures.
        """
        batch = self._get_batch_internal(batch_id)
        if batch is None:
            return BatchResult(
                batch_id=batch_id, errors=["Batch not found"],
            )

        if batch.status != "pending":
            return BatchResult(
                batch_id=batch_id,
                errors=[f"Batch is already {batch.status}"],
            )

        from .chain import get_approval_chain
        chain = get_approval_chain()

        approved = 0
        errors: List[str] = []
        individual_results: List[Dict[str, Any]] = []

        for idx, request_id in enumerate(batch.request_ids):
            result = chain.approve(request_id, approver_id, approver_role)
            individual_results.append({
                "index": idx,
                "request_id": request_id,
                "success": result.success,
                "message": result.message,
                "status": result.status.value,
            })
            if result.success:
                approved += 1
            else:
                errors.append(f"Index {idx} ({request_id}): {result.message}")

        batch.approved_count = approved
        batch.rejected_count = batch.total_count - approved
        batch.status = "approved" if approved == batch.total_count else "partial"

        with self._lock:
            self._persist_batch(batch, insert=False)

        logger.info(
            "BatchApproval: Batch %s approved %d/%d",
            batch_id, approved, batch.total_count,
        )
        return BatchResult(
            batch_id=batch_id,
            total=batch.total_count,
            approved=approved,
            rejected=batch.rejected_count,
            errors=errors,
            individual_results=individual_results,
        )

    def reject_batch(
        self,
        batch_id: str,
        approver_id: int,
        reason: str = "",
    ) -> BatchResult:
        """Reject ALL pending requests in the batch.

        Uses ApprovalChain.reject() for each individual request.
        """
        batch = self._get_batch_internal(batch_id)
        if batch is None:
            return BatchResult(
                batch_id=batch_id, errors=["Batch not found"],
            )

        if batch.status != "pending":
            return BatchResult(
                batch_id=batch_id,
                errors=[f"Batch is already {batch.status}"],
            )

        from .chain import get_approval_chain
        chain = get_approval_chain()

        rejected = 0
        errors: List[str] = []
        individual_results: List[Dict[str, Any]] = []

        for idx, request_id in enumerate(batch.request_ids):
            result = chain.reject(request_id, approver_id, reason=reason)
            individual_results.append({
                "index": idx,
                "request_id": request_id,
                "success": result.success,
                "message": result.message,
                "status": result.status.value,
            })
            if result.success:
                rejected += 1
            else:
                errors.append(f"Index {idx} ({request_id}): {result.message}")

        batch.rejected_count = rejected
        batch.approved_count = 0
        batch.status = "rejected" if rejected == batch.total_count else "partial"

        with self._lock:
            self._persist_batch(batch, insert=False)

        logger.info(
            "BatchApproval: Batch %s rejected %d/%d",
            batch_id, rejected, batch.total_count,
        )
        return BatchResult(
            batch_id=batch_id,
            total=batch.total_count,
            approved=0,
            rejected=rejected,
            errors=errors,
            individual_results=individual_results,
        )

    def approve_partial(
        self,
        batch_id: str,
        approver_id: int,
        approver_role: str,
        indices: List[int],
    ) -> BatchResult:
        """Approve only the specified indices within the batch.

        Remaining items stay in their current status.
        """
        batch = self._get_batch_internal(batch_id)
        if batch is None:
            return BatchResult(
                batch_id=batch_id, errors=["Batch not found"],
            )

        if batch.status not in ("pending", "partial"):
            return BatchResult(
                batch_id=batch_id,
                errors=[f"Batch is already {batch.status}"],
            )

        from .chain import get_approval_chain
        chain = get_approval_chain()

        approved = 0
        errors: List[str] = []
        individual_results: List[Dict[str, Any]] = []

        for idx in indices:
            if idx < 0 or idx >= len(batch.request_ids):
                errors.append(f"Index {idx} out of range (0–{len(batch.request_ids) - 1})")
                continue
            request_id = batch.request_ids[idx]
            result = chain.approve(request_id, approver_id, approver_role)
            individual_results.append({
                "index": idx,
                "request_id": request_id,
                "success": result.success,
                "message": result.message,
                "status": result.status.value,
            })
            if result.success:
                approved += 1
            else:
                errors.append(f"Index {idx} ({request_id}): {result.message}")

        batch.approved_count += approved
        if batch.approved_count + batch.rejected_count >= batch.total_count:
            batch.status = "completed"
        else:
            batch.status = "partial"

        with self._lock:
            self._persist_batch(batch, insert=False)

        logger.info(
            "BatchApproval: Batch %s partial-approve %d items",
            batch_id, approved,
        )
        return BatchResult(
            batch_id=batch_id,
            total=batch.total_count,
            approved=approved,
            rejected=0,
            errors=errors,
            individual_results=individual_results,
        )

    # ── Query Methods ──────────────────────────────────────

    def get_batch(self, batch_id: str) -> Optional[BatchRequest]:
        """Get a batch by ID."""
        return self._get_batch_internal(batch_id)

    def list_batches(
        self, status: str = "", limit: int = 20,
    ) -> List[BatchRequest]:
        """List batches, optionally filtered by status."""
        def _do_query() -> List[BatchRequest]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    """SELECT * FROM batch_requests
                       WHERE status = ?
                       ORDER BY created_at DESC LIMIT ?""",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM batch_requests
                       ORDER BY created_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
            conn.close()
            return [self._row_to_batch(r) for r in rows]

        return self._with_retry(_do_query, fallback=[])

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate batch approval statistics."""
        def _do_query() -> Dict[str, Any]:
            conn = sqlite3.connect(self._db_path)
            try:
                total = conn.execute(
                    "SELECT COUNT(*) FROM batch_requests"
                ).fetchone()[0]
                total_approved = conn.execute(
                    "SELECT SUM(approved_count) FROM batch_requests"
                ).fetchone()[0] or 0
                total_rejected = conn.execute(
                    "SELECT SUM(rejected_count) FROM batch_requests"
                ).fetchone()[0] or 0
                by_status: Dict[str, int] = {}
                for st in ("pending", "approved", "rejected", "partial", "completed"):
                    cnt = conn.execute(
                        "SELECT COUNT(*) FROM batch_requests WHERE status = ?",
                        (st,),
                    ).fetchone()[0]
                    by_status[st] = cnt
            finally:
                conn.close()
            return {
                "total_batches": total,
                "total_items_approved": total_approved,
                "total_items_rejected": total_rejected,
                "by_status": by_status,
            }

        return self._with_retry(_do_query, fallback={})

    # ── Private Helpers ────────────────────────────────────

    def _get_batch_internal(self, batch_id: str) -> Optional[BatchRequest]:
        """Retrieve a batch from the database."""
        def _do_find() -> Optional[BatchRequest]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM batch_requests WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return self._row_to_batch(row)

        return self._with_retry(_do_find, fallback=None)

    def _persist_batch(self, batch: BatchRequest, *, insert: bool) -> None:
        """Insert or update a batch in the database."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            if insert:
                conn.execute(
                    """INSERT INTO batch_requests
                       (batch_id, action_type, action_configs, requested_by,
                        required_role, status, total_count, approved_count,
                        rejected_count, request_ids, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        batch.batch_id, batch.action_type,
                        json.dumps(batch.action_configs),
                        batch.requested_by, batch.required_role,
                        batch.status, batch.total_count,
                        batch.approved_count, batch.rejected_count,
                        json.dumps(batch.request_ids),
                        batch.created_at,
                    ),
                )
            else:
                conn.execute(
                    """UPDATE batch_requests SET
                       status=?, approved_count=?, rejected_count=?, request_ids=?
                       WHERE batch_id=?""",
                    (
                        batch.status, batch.approved_count,
                        batch.rejected_count, json.dumps(batch.request_ids),
                        batch.batch_id,
                    ),
                )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)

    @staticmethod
    def _row_to_batch(row: sqlite3.Row) -> BatchRequest:
        """Convert a database row to a BatchRequest."""
        return BatchRequest(
            batch_id=row["batch_id"],
            action_type=row["action_type"],
            action_configs=json.loads(row["action_configs"] or "[]"),
            requested_by=row["requested_by"],
            required_role=row["required_role"],
            status=row["status"],
            total_count=row["total_count"],
            approved_count=row["approved_count"],
            rejected_count=row["rejected_count"],
            request_ids=json.loads(row["request_ids"] or "[]"),
            created_at=row["created_at"],
        )

    @staticmethod
    def _with_retry(
        fn: Any,
        fallback: Any = None,
        max_retries: int = _MAX_RETRIES,
    ) -> Any:
        """Execute *fn* with retry logic on database errors."""
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                return fn()
            except sqlite3.OperationalError as exc:
                last_exc = exc
                logger.warning(
                    "BatchApproval: DB retry %d/%d — %s", attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    time.sleep(_RETRY_DELAY * attempt)
            except Exception as exc:
                last_exc = exc
                logger.error("BatchApproval: DB error — %s", exc)
                break
        logger.error("BatchApproval: All retries exhausted — %s", last_exc)
        return fallback


# ── Singleton ─────────────────────────────────────────────

_batch_instance: Optional[BatchApprovalEngine] = None
_batch_lock = threading.Lock()


def get_batch_approval(db_path: str = "batch_approval.sqlite") -> BatchApprovalEngine:
    """Get or create the global BatchApprovalEngine instance."""
    global _batch_instance
    with _batch_lock:
        if _batch_instance is None:
            _batch_instance = BatchApprovalEngine(db_path=db_path)
        return _batch_instance


def reset_batch_approval() -> None:
    """Reset the global BatchApprovalEngine (for testing)."""
    global _batch_instance
    _batch_instance = None


__all__ = [
    "BatchRequest",
    "BatchResult",
    "BatchApprovalEngine",
    "get_batch_approval",
    "reset_batch_approval",
]
