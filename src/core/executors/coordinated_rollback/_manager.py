"""
ZENIC-AGENTS - Coordinated Rollback Manager

Multi-resource coordinated rollback using SAGA-style compensation.

When a multi-step action touches several resources (DB, email, file,
webhook), the CoordinatedRollbackManager records every operation and
can roll them all back in **reverse order** if the action fails.

Thread-safe.  Persists actions to SQLite for crash recovery.
Every operation is wrapped in retry logic.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import uuid
from typing import Any, Dict, List, Optional

from src.core.shared.retry import with_retry
from src.core.shared.db_initializer import get_data_dir
from src.core.executors.coordinated_rollback._types import (
    ResourceType,
    ActionStatus,
    ResourceRecord,
    CoordinatedAction,
    CoordinatedRollbackResult,
)
from src.core.executors.coordinated_rollback._compensation import (
    execute_compensation,
)
from src.core.executors.coordinated_rollback._persistence import (
    init_db,
    persist_action,
    add_record,
    mark_record_compensated,
    update_action_status,
    load_action,
    list_active_action_ids,
)

logger = logging.getLogger(__name__)


class CoordinatedRollbackManager:
    """Manages coordinated rollback across multiple resource types.

    Records every operation (DB write, email sent, file modified,
    webhook called) and can roll them all back in reverse order
    using SAGA-style compensation.

    Thread-safe.  Persists actions to SQLite for crash recovery.
    Every operation is wrapped in retry logic.
    """

    _DB_NAME = "coordinated_rollback.sqlite"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._db_path = str(get_data_dir() / self._DB_NAME)
        init_db(self._db_path)

    # ── Core public API ──────────────────────────────────────

    def begin_coordinated_action(
        self,
        action_id: str,
        tenant_id: str,
    ) -> CoordinatedAction:
        """Start tracking a multi-resource action.

        Args:
            action_id: A caller-provided identifier for the action.
            tenant_id: The tenant that owns this action.

        Returns:
            A new ``CoordinatedAction`` in ``IN_PROGRESS`` status.
        """
        action = CoordinatedAction(
            action_id=action_id,
            tenant_id=tenant_id,
        )
        persist_action(self._db_path, action)

        logger.info(
            "CoordinatedRollbackManager: began action %s [tenant=%s]",
            action_id[:12], tenant_id,
        )
        return action

    def record_db_action(self, action_id: str, journal_id: str) -> None:
        """Record that a DB operation was performed.

        Args:
            action_id: The coordinated action to attach the record to.
            journal_id: The journal entry ID from DBTransactionJournal.
        """
        record = ResourceRecord(
            resource_type=ResourceType.DB,
            resource_id=journal_id,
            rollback_data={"journal_id": journal_id},
        )
        with self._lock:
            add_record(self._db_path, action_id, record)
        logger.debug(
            "CoordinatedRollbackManager: recorded DB action journal=%s for action=%s",
            journal_id[:12], action_id[:12],
        )

    def record_email_action(
        self,
        action_id: str,
        config: Dict[str, Any],
    ) -> None:
        """Record that an email was sent.

        Args:
            action_id: The coordinated action to attach the record to.
            config: Email configuration (to, subject, etc.) for recall log.
        """
        record = ResourceRecord(
            resource_type=ResourceType.EMAIL,
            resource_id=config.get("message_id", uuid.uuid4().hex[:12]),
            rollback_data=config,
        )
        with self._lock:
            add_record(self._db_path, action_id, record)
        logger.debug(
            "CoordinatedRollbackManager: recorded email action for action=%s",
            action_id[:12],
        )

    def record_file_action(
        self,
        action_id: str,
        operation: str,
        source: str,
        backup_path: str,
    ) -> None:
        """Record a file operation with its backup.

        Args:
            action_id: The coordinated action to attach the record to.
            operation: The file operation (create, modify, delete).
            source: The path of the file that was modified.
            backup_path: Path to the backup copy for restoration.
        """
        record = ResourceRecord(
            resource_type=ResourceType.FILE,
            resource_id=source,
            rollback_data={
                "operation": operation,
                "source": source,
                "backup_path": backup_path,
            },
        )
        with self._lock:
            add_record(self._db_path, action_id, record)
        logger.debug(
            "CoordinatedRollbackManager: recorded file action op=%s source=%s for action=%s",
            operation, source, action_id[:12],
        )

    def record_webhook_action(
        self,
        action_id: str,
        url: str,
        payload: Dict[str, Any],
    ) -> None:
        """Record a webhook call.

        Args:
            action_id: The coordinated action to attach the record to.
            url: The webhook endpoint URL.
            payload: The payload that was sent.
        """
        record = ResourceRecord(
            resource_type=ResourceType.WEBHOOK,
            resource_id=url,
            rollback_data={
                "url": url,
                "payload": payload,
                "cancellation_url": url,  # Assume same endpoint supports cancellation
            },
        )
        with self._lock:
            add_record(self._db_path, action_id, record)
        logger.debug(
            "CoordinatedRollbackManager: recorded webhook action url=%s for action=%s",
            url[:50], action_id[:12],
        )

    def commit_action(self, action_id: str) -> None:
        """Mark the action as committed (no rollback needed).

        Args:
            action_id: The action to commit.
        """
        with self._lock:
            update_action_status(self._db_path, action_id, ActionStatus.COMMITTED)
            logger.info(
                "CoordinatedRollbackManager: committed action %s",
                action_id[:12],
            )

    def rollback_action(
        self,
        action_id: str,
        reason: str,
    ) -> CoordinatedRollbackResult:
        """Perform coordinated rollback across all recorded resources.

        Compensation is executed in **reverse order** (last action
        rolled back first).  If one compensation fails, the manager
        continues with the rest and records the failure.

        Args:
            action_id: The action to roll back.
            reason: A human-readable reason for the rollback.

        Returns:
            A ``CoordinatedRollbackResult`` with details.
        """
        with self._lock:
            action = load_action(self._db_path, action_id)
            if action is None:
                return CoordinatedRollbackResult(
                    success=False,
                    action_id=action_id,
                    errors=[f"Action {action_id} not found"],
                )

            if action.status == ActionStatus.COMMITTED:
                return CoordinatedRollbackResult(
                    success=False,
                    action_id=action_id,
                    errors=[f"Action {action_id} is already committed"],
                )

            if action.status == ActionStatus.ROLLED_BACK:
                return CoordinatedRollbackResult(
                    success=False,
                    action_id=action_id,
                    errors=[f"Action {action_id} is already rolled back"],
                )

            logger.info(
                "CoordinatedRollbackManager: rolling back action %s reason=%s",
                action_id[:12], reason,
            )

            result = CoordinatedRollbackResult(action_id=action_id)

            # Rollback in REVERSE order (last action first)
            for record in reversed(action.records):
                if record.compensation_executed:
                    continue

                result.compensations_attempted += 1
                try:
                    execute_compensation(action_id, record, self._db_path)
                    record.compensation_executed = True
                    mark_record_compensated(self._db_path, action_id, record)
                    result.compensations_succeeded += 1
                except Exception as exc:
                    error_msg = (
                        f"Compensation failed for {record.resource_type.value}"
                        f" ({record.resource_id}): {exc}"
                    )
                    result.errors.append(error_msg)
                    logger.error(
                        "CoordinatedRollbackManager: %s", error_msg,
                    )
                    # Continue with the rest (best-effort)

            # Update action status
            update_action_status(self._db_path, action_id, ActionStatus.ROLLED_BACK)

            result.success = len(result.errors) == 0
            logger.info(
                "CoordinatedRollbackManager: rollback complete action=%s "
                "attempted=%d succeeded=%d errors=%d",
                action_id[:12],
                result.compensations_attempted,
                result.compensations_succeeded,
                len(result.errors),
            )
            return result

    def get_action(self, action_id: str) -> Optional[CoordinatedAction]:
        """Retrieve a coordinated action by its ID.

        Args:
            action_id: The unique action identifier.

        Returns:
            The ``CoordinatedAction`` if found, else ``None``.
        """
        return load_action(self._db_path, action_id)

    def list_active_actions(self, tenant_id: str) -> List[CoordinatedAction]:
        """List all in-progress actions for a tenant.

        Args:
            tenant_id: The tenant to filter by.

        Returns:
            A list of ``CoordinatedAction`` objects.
        """
        action_ids = list_active_action_ids(self._db_path, tenant_id)
        actions: List[CoordinatedAction] = []
        for aid in action_ids:
            action = load_action(self._db_path, aid)
            if action is not None:
                actions.append(action)
        return actions


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

_instance: Optional[CoordinatedRollbackManager] = None
_instance_lock = threading.Lock()


def get_coordinated_rollback_manager() -> CoordinatedRollbackManager:
    """Return the singleton CoordinatedRollbackManager instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = CoordinatedRollbackManager()
    return _instance


def reset_coordinated_rollback_manager() -> None:
    """Reset the singleton instance (mainly for testing)."""
    global _instance
    with _instance_lock:
        _instance = None
