"""
coordinated_rollback._mixin_core — Core public API mixin for CoordinatedRollbackManager.
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

from src.core.shared.retry import with_retry
from src.core.shared.db_initializer import get_data_dir
from src.core.executors.coordinated_rollback._types import (
    ActionStatus,
    CoordinatedAction,
    CoordinatedRollbackResult,
    ResourceRecord,
    ResourceType,
)

logger = logging.getLogger(__name__)


class CoreMixin:
    """Mixin providing core public API and schema initialisation."""

    # These attributes are provided by the main class; declared for type checkers.
    _db_path: str
    _lock: object

    _DB_NAME: str = "coordinated_rollback.sqlite"

    def _init_db(self) -> None:
        """Create the SQLite tables if they do not exist."""

        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """
                    CREATE TABLE IF NOT EXISTS coordinated_actions (
                        action_id  TEXT PRIMARY KEY,
                        tenant_id  TEXT NOT NULL,
                        status     TEXT NOT NULL DEFAULT 'in_progress',
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "CREATE INDEX IF NOT EXISTS idx_ca_tenant "
                    "ON coordinated_actions(tenant_id)"
                )
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "CREATE INDEX IF NOT EXISTS idx_ca_status "
                    "ON coordinated_actions(status)"
                )
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """
                    CREATE TABLE IF NOT EXISTS resource_records (
                        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                        action_id             TEXT NOT NULL,
                        resource_type         TEXT NOT NULL,
                        resource_id           TEXT NOT NULL DEFAULT '',
                        rollback_data         TEXT NOT NULL DEFAULT '{}',
                        compensation_executed INTEGER NOT NULL DEFAULT 0,
                        created_at            REAL NOT NULL,
                        FOREIGN KEY (action_id) REFERENCES coordinated_actions(action_id)
                    )
                    """
                )
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "CREATE INDEX IF NOT EXISTS idx_rr_action "
                    "ON resource_records(action_id)"
                )
                conn.commit()
            finally:
                conn.close()

        with_retry(
            _do_init,
            max_retries=3,
            base_delay=0.5,
            label="coordinated_rollback._init_db",
        )
        logger.debug(
            "CoordinatedRollbackManager: schema initialised at %s", self._db_path
        )

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

        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """
                    INSERT INTO coordinated_actions
                        (action_id, tenant_id, status, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (action.action_id, action.tenant_id, action.status.value, action.created_at),
                )
                conn.commit()
            finally:
                conn.close()

        with_retry(
            _do_persist,
            max_retries=3,
            base_delay=0.5,
            label=f"coordinated_rollback.begin({action_id[:12]})",
        )

        logger.info(
            "CoordinatedRollbackManager: began action %s [tenant=%s]",
            action_id[:12], tenant_id,
        )
        return action

    def record_db_action(self, action_id: str, journal_id: str) -> None:
        """Record that a DB operation was performed."""
        record = ResourceRecord(
            resource_type=ResourceType.DB,
            resource_id=journal_id,
            rollback_data={"journal_id": journal_id},
        )
        self._add_record(action_id, record)
        logger.debug(
            "CoordinatedRollbackManager: recorded DB action journal=%s for action=%s",
            journal_id[:12], action_id[:12],
        )

    def record_email_action(
        self,
        action_id: str,
        config: Dict[str, Any],
    ) -> None:
        """Record that an email was sent."""
        record = ResourceRecord(
            resource_type=ResourceType.EMAIL,
            resource_id=config.get("message_id", uuid.uuid4().hex[:12]),
            rollback_data=config,
        )
        self._add_record(action_id, record)
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
        """Record a file operation with its backup."""
        record = ResourceRecord(
            resource_type=ResourceType.FILE,
            resource_id=source,
            rollback_data={
                "operation": operation,
                "source": source,
                "backup_path": backup_path,
            },
        )
        self._add_record(action_id, record)
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
        """Record a webhook call."""
        record = ResourceRecord(
            resource_type=ResourceType.WEBHOOK,
            resource_id=url,
            rollback_data={
                "url": url,
                "payload": payload,
                "cancellation_url": url,  # Assume same endpoint supports cancellation
            },
        )
        self._add_record(action_id, record)
        logger.debug(
            "CoordinatedRollbackManager: recorded webhook action url=%s for action=%s",
            url[:50], action_id[:12],
        )

    def commit_action(self, action_id: str) -> None:
        """Mark the action as committed (no rollback needed)."""
        with self._lock:
            self._update_action_status(action_id, ActionStatus.COMMITTED)
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
        """
        with self._lock:
            action = self._load_action(action_id)
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
                    self._execute_compensation(action_id, record)
                    record.compensation_executed = True
                    self._mark_record_compensated(action_id, record)
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
            self._update_action_status(action_id, ActionStatus.ROLLED_BACK)

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
        """Retrieve a coordinated action by its ID."""

        def _do_get() -> Optional[CoordinatedAction]:
            return self._load_action(action_id)

        return with_retry(
            _do_get,
            max_retries=3,
            base_delay=0.5,
            label=f"coordinated_rollback.get_action({action_id[:12]})",
        )

    def list_active_actions(self, tenant_id: str) -> List[CoordinatedAction]:
        """List all in-progress actions for a tenant."""

        def _do_list() -> List[CoordinatedAction]:
            conn = sqlite3.connect(self._db_path)
            try:
                cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """
                    SELECT action_id FROM coordinated_actions
                    WHERE tenant_id = ? AND status = ?
                    ORDER BY created_at DESC
                    """,
                    (tenant_id, ActionStatus.IN_PROGRESS.value),
                )
                action_ids = [row[0] for row in cursor.fetchall()]
                actions: List[CoordinatedAction] = []
                for aid in action_ids:
                    action = self._load_action(aid)
                    if action is not None:
                        actions.append(action)
                return actions
            finally:
                conn.close()

        return with_retry(
            _do_list,
            max_retries=3,
            base_delay=0.5,
            label="coordinated_rollback.list_active_actions",
        )
