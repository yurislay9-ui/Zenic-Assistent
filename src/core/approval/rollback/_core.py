"""rollback — Core implementation."""

from __future__ import annotations

from ._types import *  # noqa: F403
from ._helpers import _init_db, _get_compensations, _execute_compensation_action, _record_in_merkle_ledger, _record_audit_event, _persist_compensation, _persist_rollback_record, _row_to_compensation, _row_to_rollback_record, _with_retry

class RollbackManager:
    """Manages compensation actions and rollback execution.

    SAGA-inspired: when an approved action is undone, all compensation
    actions are executed in reverse order.
    """

    def __init__(self, db_path: str = "rollback.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    # ── DB Initialisation ──────────────────────────────────

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
            self._persist_compensation(request_id, action, insert=True)

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
        actions = self._get_compensations(request_id)

        # Create the rollback record
        record = RollbackRecord(
            request_id=request_id,
            trigger=trigger,
            compensation_actions=actions,
            status=RollbackStatus.EXECUTING,
        )

        with self._lock:
            self._persist_rollback_record(record, insert=True)

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

        record.executed_at = datetime.now(timezone.utc).isoformat()
        record.status = RollbackStatus.COMPLETED if all_succeeded else RollbackStatus.FAILED
        record.result = {"actions": results}

        with self._lock:
            self._persist_rollback_record(record, insert=False)

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
        def _do_find() -> Optional[RollbackRecord]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM rollback_records WHERE rollback_id = ?",
                (rollback_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return self._row_to_rollback_record(row)

        return self._with_retry(_do_find, fallback=None)

    def get_rollback_history(self, request_id: str) -> List[RollbackRecord]:
        """Get all rollback records for a request."""
        def _do_query() -> List[RollbackRecord]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """SELECT * FROM rollback_records
                   WHERE request_id = ?
                   ORDER BY created_at DESC""",
                (request_id,),
            ).fetchall()
            conn.close()
            return [self._row_to_rollback_record(r) for r in rows]

        return self._with_retry(_do_query, fallback=[])

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

    @staticmethod
    @staticmethod
    @staticmethod