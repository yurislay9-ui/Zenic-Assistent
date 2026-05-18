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

import json
import logging
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from ._snapshots import (
    CompensationAction,
    RollbackRecord,
    RollbackStatus,
    RollbackTrigger,
)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1


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

    def _init_db(self) -> None:
        """Create the rollback tables if they do not exist."""
        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS compensation_actions (
                    action_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    description TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS rollback_records (
                    rollback_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    compensation_actions TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'pending',
                    executed_at TEXT,
                    result TEXT,
                    created_at TEXT NOT NULL,
                    merkle_hash TEXT NOT NULL
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_compensation_request
                ON compensation_actions(request_id)
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_rollback_request
                ON rollback_records(request_id, created_at DESC)
            """)
            conn.commit()
            conn.close()

        self._with_retry(_do_init)

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

        record.executed_at = self._now_utc_iso()
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
    def _now_utc_iso() -> str:
        """Return current UTC time as ISO string."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    def _get_compensations(self, request_id: str) -> List[CompensationAction]:
        """Get all compensation actions for a request."""
        def _do_query() -> List[CompensationAction]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """SELECT * FROM compensation_actions
                   WHERE request_id = ?
                   ORDER BY action_id ASC""",
                (request_id,),
            ).fetchall()
            conn.close()
            return [self._row_to_compensation(r) for r in rows]

        return self._with_retry(_do_query, fallback=[])

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

    def _persist_compensation(
        self, request_id: str, action: CompensationAction, *, insert: bool,
    ) -> None:
        """Insert or update a compensation action."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            if insert:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT INTO compensation_actions
                       (action_id, request_id, action_type, payload, description)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        action.action_id,
                        request_id,
                        action.action_type,
                        json.dumps(action.payload),
                        action.description,
                    ),
                )
            else:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """UPDATE compensation_actions SET
                       payload=?, description=?
                       WHERE action_id=?""",
                    (
                        json.dumps(action.payload),
                        action.description,
                        action.action_id,
                    ),
                )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)

    def _persist_rollback_record(
        self, record: RollbackRecord, *, insert: bool,
    ) -> None:
        """Insert or update a rollback record."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            actions_json = json.dumps([a.to_dict() for a in record.compensation_actions])
            result_json = json.dumps(record.result) if record.result else None

            if insert:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT INTO rollback_records
                       (rollback_id, request_id, trigger,
                        compensation_actions, status, executed_at,
                        result, created_at, merkle_hash)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.rollback_id,
                        record.request_id,
                        record.trigger.value,
                        actions_json,
                        record.status.value,
                        record.executed_at,
                        result_json,
                        record.created_at,
                        record.merkle_hash,
                    ),
                )
            else:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """UPDATE rollback_records SET
                       status=?, executed_at=?, result=?,
                       merkle_hash=?
                       WHERE rollback_id=?""",
                    (
                        record.status.value,
                        record.executed_at,
                        result_json,
                        record.merkle_hash,
                        record.rollback_id,
                    ),
                )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)

    @staticmethod
    def _row_to_compensation(row: sqlite3.Row) -> CompensationAction:
        """Convert a database row to a CompensationAction."""
        return CompensationAction(
            action_id=row["action_id"],
            action_type=row["action_type"],
            payload=json.loads(row["payload"] or "{}"),
            description=row["description"] or "",
        )

    @staticmethod
    def _row_to_rollback_record(row: sqlite3.Row) -> RollbackRecord:
        """Convert a database row to a RollbackRecord."""
        actions_data = json.loads(row["compensation_actions"] or "[]")
        result_data = json.loads(row["result"]) if row["result"] else None
        return RollbackRecord(
            rollback_id=row["rollback_id"],
            request_id=row["request_id"],
            trigger=RollbackTrigger(row["trigger"]),
            compensation_actions=[CompensationAction.from_dict(a) for a in actions_data],
            status=RollbackStatus(row["status"]),
            executed_at=row["executed_at"],
            result=result_data,
            created_at=row["created_at"],
            merkle_hash=row["merkle_hash"],
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
                    "RollbackManager: DB retry %d/%d — %s",
                    attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    time.sleep(_RETRY_DELAY * attempt)
            except Exception as exc:
                last_exc = exc
                logger.error("RollbackManager: DB error — %s", exc)
                break
        logger.error("RollbackManager: All retries exhausted — %s", last_exc)
        return fallback


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
