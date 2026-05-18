"""
Batch Approval Engine — Core Mixin.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, List, Optional

from ._types import BatchRequest, BatchResult
from ._mixin_persistence import BatchPersistenceMixin

logger = logging.getLogger(__name__)


class BatchApprovalEngine(BatchPersistenceMixin):
    """Approve or reject multiple similar actions at once.

    Each batch creates individual ApprovalChain requests so that
    the existing audit trail and role checks are preserved.
    """

    def __init__(self, db_path: str = "batch_approval.sqlite") -> None:
        self._db_path = db_path
        self._lock: Any = None  # set in __init__ but type declared for mixin compat
        import threading
        self._lock = threading.RLock()
        self._init_db()

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
        """
        if not action_configs:
            raise ValueError("Cannot create a batch with empty action_configs")

        for i, cfg in enumerate(action_configs):
            cfg_action = cfg.get("action_type", "")
            if cfg_action and cfg_action != action_type:
                raise ValueError(
                    f"Config at index {i} has action_type '{cfg_action}' "
                    f"which does not match batch action_type '{action_type}'"
                )

        # Lazy import to avoid circular dependency
        from ..chain import get_approval_chain

        chain = get_approval_chain()

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
        """Approve ALL pending requests in the batch."""
        batch = self._get_batch_internal(batch_id)
        if batch is None:
            return BatchResult(batch_id=batch_id, errors=["Batch not found"])

        if batch.status != "pending":
            return BatchResult(
                batch_id=batch_id,
                errors=[f"Batch is already {batch.status}"],
            )

        from ..chain import get_approval_chain
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
        """Reject ALL pending requests in the batch."""
        batch = self._get_batch_internal(batch_id)
        if batch is None:
            return BatchResult(batch_id=batch_id, errors=["Batch not found"])

        if batch.status != "pending":
            return BatchResult(
                batch_id=batch_id,
                errors=[f"Batch is already {batch.status}"],
            )

        from ..chain import get_approval_chain
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
        """Approve only the specified indices within the batch."""
        batch = self._get_batch_internal(batch_id)
        if batch is None:
            return BatchResult(batch_id=batch_id, errors=["Batch not found"])

        if batch.status not in ("pending", "partial"):
            return BatchResult(
                batch_id=batch_id,
                errors=[f"Batch is already {batch.status}"],
            )

        from ..chain import get_approval_chain
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
                rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """SELECT * FROM batch_requests
                       WHERE status = ?
                       ORDER BY created_at DESC LIMIT ?""",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
                total = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT COUNT(*) FROM batch_requests"
                ).fetchone()[0]
                total_approved = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT SUM(approved_count) FROM batch_requests"
                ).fetchone()[0] or 0
                total_rejected = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT SUM(rejected_count) FROM batch_requests"
                ).fetchone()[0] or 0
                by_status: Dict[str, int] = {}
                for st in ("pending", "approved", "rejected", "partial", "completed"):
                    cnt = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
