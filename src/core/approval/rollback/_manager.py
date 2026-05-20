"""
Zenic-Agents Asistente - Rollback Manager (Phase 5)

SAGA-inspired compensation pattern for reverting approved actions.
When an approved action needs to be undone, all registered compensation
actions are executed in reverse order.

Triggers:
  - APPROVAL_EXPIRED: The approval expired and needs auto-revert
  - ACTION_FAILED: The approved action failed during execution
  - MANUAL_UNDO: A user explicitly requested an undo
  - COMPLIANCE_VIOLATION: A compliance check post-approval failed

Integration:
  - Called by ExpiryManager.execute_revert() and by the undo API.
  - Each rollback is hashed into the Merkle ledger for immutability.

Persistence: SQLite with retry logic.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from ._db_helpers import (
    get_compensations,
    get_rollback_history as _get_rollback_history_db,
    get_rollback_record_by_id,
    init_db,
    now_utc_iso,
    persist_compensation,
    persist_rollback_record,
)
from ._snapshots import (
    CompensationAction,
    RollbackRecord,
    RollbackStatus,
    RollbackTrigger,
)

logger = logging.getLogger(__name__)


class RollbackManager:
    """Manages compensation actions and rollback execution.

    SAGA-inspired: when an approved action is undone, all compensation
    actions are executed in reverse order.
    """

    def __init__(self, db_path: str = "rollback.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        init_db(db_path)

    # ── Core Operations ────────────────────────────────────

    def register_compensation(
        self,
        request_id: str,
        action_type: str,
        payload: Dict[str, Any],
        description: str = "",
    ) -> CompensationAction:
        """Register a compensation action for a request.

        Compensation actions are executed in reverse order during rollback.

        Args:
            request_id: The approval request ID.
            action_type: Type of compensation action (e.g., "restore_state").
            payload: Data needed to execute the compensation.
            description: Human-readable description.

        Returns:
            The created CompensationAction.
        """
        if not request_id:
            raise ValueError("request_id is required")
        if not action_type:
            raise ValueError("action_type is required")

        action = CompensationAction(
            action_type=action_type,
            payload=payload,
            description=description,
        )

        with self._lock:
            persist_compensation(
                self._db_path, request_id, action, insert=True,
            )

        logger.info(
            "RollbackManager: Registered compensation %s for request %s "
            "(type=%s)",
            action.action_id, request_id, action_type,
        )
        return action

    def execute_rollback(
        self,
        request_id: str,
        trigger: RollbackTrigger,
        merkle_ledger: Any = None,
    ) -> RollbackRecord:
        """Execute a rollback for a request.

        Executes all registered compensation actions in reverse order.
        If merkle_ledger is provided, records the rollback in the Merkle ledger.

        Args:
            request_id: The approval request ID to rollback.
            trigger: What triggered the rollback.
            merkle_ledger: Optional Merkle ledger for recording the rollback.

        Returns:
            The RollbackRecord with execution results.
        """
        # Get all compensation actions for this request
        actions = get_compensations(self._db_path, request_id)

        # Create the rollback record
        record = RollbackRecord(
            request_id=request_id,
            trigger=trigger,
            compensation_actions=actions,
            status=RollbackStatus.EXECUTING,
        )

        with self._lock:
            persist_rollback_record(self._db_path, record, insert=True)

        # Execute compensation actions in reverse order (SAGA pattern)
        results: List[Dict[str, Any]] = []
        all_succeeded = True

        for action in reversed(actions):
            try:
                result = self._execute_compensation_action(action)
                results.append({
                    "action_id": action.action_id,
                    "action_type": action.action_type,
                    "success": True,
                    "result": result,
                })
                logger.info(
                    "RollbackManager: Executed compensation %s (%s)",
                    action.action_id, action.action_type,
                )
            except Exception as exc:
                all_succeeded = False
                results.append({
                    "action_id": action.action_id,
                    "action_type": action.action_type,
                    "success": False,
                    "error": str(exc),
                })
                logger.warning(
                    "RollbackManager: Compensation %s failed — %s",
                    action.action_id, exc,
                )
                # Continue executing remaining compensations even on failure

        record.executed_at = now_utc_iso()
        record.status = RollbackStatus.COMPLETED if all_succeeded else RollbackStatus.FAILED
        record.result = {"actions": results}

        with self._lock:
            persist_rollback_record(self._db_path, record, insert=False)

        # Record in Merkle ledger if provided
        if merkle_ledger is not None:
            try:
                self._record_in_merkle_ledger(merkle_ledger, record)
            except Exception as exc:
                logger.warning("RollbackManager: Merkle ledger recording failed: %s", exc)

        # Record audit event
        self._record_audit_event(request_id, record)

        logger.info(
            "RollbackManager: Rollback %s for request %s — status=%s "
            "(%d/%d actions succeeded)",
            record.rollback_id, request_id, record.status.value,
            sum(1 for r in results if r.get("success")),
            len(results),
        )
        return record

    def get_rollback_record(self, rollback_id: str) -> Optional[RollbackRecord]:
        """Get a rollback record by ID."""
        return get_rollback_record_by_id(self._db_path, rollback_id)

    def get_rollback_history(self, request_id: str) -> List[RollbackRecord]:
        """Get all rollback records for a request."""
        return _get_rollback_history_db(self._db_path, request_id)

    def verify_rollback_integrity(self, rollback_id: str) -> bool:
        """Verify the Merkle hash integrity of a rollback record."""
        record = self.get_rollback_record(rollback_id)
        if record is None:
            logger.warning(
                "RollbackManager: Record %s not found for integrity check",
                rollback_id,
            )
            return False

        recomputed = record._compute_hash()
        return recomputed == record.merkle_hash

    # ── Private Helpers ────────────────────────────────────

    def _execute_compensation_action(
        self, action: CompensationAction,
    ) -> Dict[str, Any]:
        """Execute a single compensation action.

        This is a stub — real implementations would dispatch to
        specific action handlers based on action_type.
        """
        logger.info(
            "RollbackManager: Executing compensation: %s (%s) — %s",
            action.action_id, action.action_type, action.description,
        )

        # Stub: log and return success
        return {
            "action_id": action.action_id,
            "action_type": action.action_type,
            "executed": True,
            "message": f"Compensation action '{action.action_type}' executed",
        }

    def _record_in_merkle_ledger(
        self, merkle_ledger: Any, record: RollbackRecord,
    ) -> None:
        """Record the rollback in the Merkle ledger."""
        # The merkle_ledger parameter is expected to be an object with
        # an append() method or similar interface from level7_merkle_ledger
        if hasattr(merkle_ledger, "append"):
            merkle_ledger.append({
                "type": "ROLLBACK_EXECUTED",
                "rollback_id": record.rollback_id,
                "request_id": record.request_id,
                "trigger": record.trigger.value,
                "merkle_hash": record.merkle_hash,
                "timestamp": record.executed_at or record.created_at,
            })
        elif hasattr(merkle_ledger, "record_event"):
            merkle_ledger.record_event(
                request_id=record.request_id,
                event_type="ROLLBACK_EXECUTED",
                actor_id="rollback_manager",
                actor_name="RollbackManager",
                details={
                    "rollback_id": record.rollback_id,
                    "trigger": record.trigger.value,
                    "merkle_hash": record.merkle_hash,
                },
            )

    def _record_audit_event(
        self, request_id: str, record: RollbackRecord,
    ) -> None:
        """Record a ROLLBACK_EXECUTED event in the audit merkle trail."""
        try:
            from ..audit_merkle import get_approval_audit_merkle
            audit = get_approval_audit_merkle()
            audit.record_event(
                request_id=request_id,
                event_type="ROLLBACK_EXECUTED",
                actor_id="rollback_manager",
                actor_name="RollbackManager",
                details={
                    "rollback_id": record.rollback_id,
                    "trigger": record.trigger.value,
                    "status": record.status.value,
                    "merkle_hash": record.merkle_hash,
                },
            )
        except Exception as exc:
            logger.debug("RollbackManager: audit event recording failed: %s", exc)


# ── Singleton ─────────────────────────────────────────────

_rollback_instance: Optional[RollbackManager] = None
_rollback_lock = threading.Lock()


def get_rollback_manager(db_path: str = "rollback.sqlite") -> RollbackManager:
    """Get or create the global RollbackManager instance."""
    global _rollback_instance
    with _rollback_lock:
        if _rollback_instance is None:
            _rollback_instance = RollbackManager(db_path=db_path)
        return _rollback_instance


def reset_rollback_manager() -> None:
    """Reset the global RollbackManager (for testing)."""
    global _rollback_instance
    _rollback_instance = None


__all__ = [
    "RollbackManager",
    "get_rollback_manager",
    "reset_rollback_manager",
]
