"""
ZENIC-AGENTS - Coordinated Rollback Manager (A3 Rollback Enhancement)

Multi-resource coordinated rollback using SAGA-style compensation.

When a multi-step action touches several resources (DB, email, file,
webhook), the CoordinatedRollbackManager records every operation and
can roll them all back in **reverse order** if the action fails.

Rollback strategies per resource type:
  - DB     → delegates to DBTransactionJournal.rollback_to()
  - Email  → logs a "recall" notification (cannot unsend emails)
  - File   → restores from backup_path if available
  - Webhook→ sends a cancellation webhook to the original endpoint

Features:
  - SQLite persistence (coordinated_rollback.sqlite) for crash recovery
  - Thread-safe via RLock
  - Every operation wrapped in retry (3 retries, 0.5s base delay)
  - Reverse-order compensation with best-effort continuation
  - Singleton pattern with get_coordinated_rollback_manager() /
    reset_coordinated_rollback_manager()
  - Proper __all__ exports
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.shared.retry import with_retry
from src.core.shared.db_initializer import get_data_dir
from src.core.executors.db_journal import DBTransactionJournal, get_db_journal
from src.core.native import (
    snapshot_file as _native_snapshot_file,
    restore_file as _native_restore_file,
    verify_rollback_readiness as _native_verify_rollback_readiness,
    file_hash as _native_file_hash,
    HAS_NATIVE as _HAS_NATIVE,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ResourceType",
    "ResourceRecord",
    "CoordinatedAction",
    "CoordinatedRollbackResult",
    "CoordinatedRollbackManager",
    "get_coordinated_rollback_manager",
    "reset_coordinated_rollback_manager",
]

# ──────────────────────────────────────────────────────────────
#  ENUMS
# ──────────────────────────────────────────────────────────────


class ResourceType(str, Enum):
    """Supported resource types for coordinated rollback."""

    DB = "db"
    EMAIL = "email"
    FILE = "file"
    WEBHOOK = "webhook"


class ActionStatus(str, Enum):
    """Lifecycle states of a CoordinatedAction."""

    IN_PROGRESS = "in_progress"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"


# ──────────────────────────────────────────────────────────────
#  DATA MODELS
# ──────────────────────────────────────────────────────────────


@dataclass
class ResourceRecord:
    """Tracks a single resource operation within a coordinated action.

    Attributes:
        resource_type: The type of resource (db, email, file, webhook).
        resource_id: Identifier for the specific resource instance
            (e.g. journal_id for DB, backup_path for file).
        rollback_data: Arbitrary data needed for rollback (JSON-serialised).
        compensation_executed: Whether the compensation has been performed.
        created_at: Unix timestamp when this record was created.
    """

    resource_type: ResourceType = ResourceType.DB
    resource_id: str = ""
    rollback_data: Dict[str, Any] = field(default_factory=dict)
    compensation_executed: bool = False
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = time.time()


@dataclass
class CoordinatedAction:
    """Represents a multi-resource action being tracked for rollback.

    Attributes:
        action_id: Unique identifier for the coordinated action.
        tenant_id: Tenant that owns this action.
        records: Ordered list of resource records (rollback is reverse).
        status: Current lifecycle status.
        created_at: Unix timestamp when the action was started.
    """

    action_id: str = ""
    tenant_id: str = ""
    records: List[ResourceRecord] = field(default_factory=list)
    status: ActionStatus = ActionStatus.IN_PROGRESS
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.action_id:
            self.action_id = uuid.uuid4().hex
        if not self.created_at:
            self.created_at = time.time()


@dataclass
class CoordinatedRollbackResult:
    """Result of a coordinated rollback operation.

    Attributes:
        success: Whether all compensations completed without errors.
        action_id: The action that was rolled back.
        compensations_attempted: Total number of compensations attempted.
        compensations_succeeded: Number that succeeded.
        errors: List of error messages from failed compensations.
    """

    success: bool = False
    action_id: str = ""
    compensations_attempted: int = 0
    compensations_succeeded: int = 0
    errors: List[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────
#  COORDINATED ROLLBACK MANAGER
# ──────────────────────────────────────────────────────────────


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
        self._init_db()

    # ── Schema initialisation ────────────────────────────────

    def _init_db(self) -> None:
        """Create the SQLite tables if they do not exist."""

        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS coordinated_actions (
                        action_id  TEXT PRIMARY KEY,
                        tenant_id  TEXT NOT NULL,
                        status     TEXT NOT NULL DEFAULT 'in_progress',
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_ca_tenant "
                    "ON coordinated_actions(tenant_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_ca_status "
                    "ON coordinated_actions(status)"
                )
                conn.execute(
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
                conn.execute(
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
                conn.execute(
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
        self._add_record(action_id, record)
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

        Args:
            action_id: The action to roll back.
            reason: A human-readable reason for the rollback.

        Returns:
            A ``CoordinatedRollbackResult`` with details.
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
        """Retrieve a coordinated action by its ID.

        Args:
            action_id: The unique action identifier.

        Returns:
            The ``CoordinatedAction`` if found, else ``None``.
        """

        def _do_get() -> Optional[CoordinatedAction]:
            return self._load_action(action_id)

        return with_retry(
            _do_get,
            max_retries=3,
            base_delay=0.5,
            label=f"coordinated_rollback.get_action({action_id[:12]})",
        )

    def list_active_actions(self, tenant_id: str) -> List[CoordinatedAction]:
        """List all in-progress actions for a tenant.

        Args:
            tenant_id: The tenant to filter by.

        Returns:
            A list of ``CoordinatedAction`` objects.
        """

        def _do_list() -> List[CoordinatedAction]:
            conn = sqlite3.connect(self._db_path)
            try:
                cursor = conn.execute(
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

    # ── Compensation executors ───────────────────────────────

    def _execute_compensation(
        self,
        action_id: str,
        record: ResourceRecord,
    ) -> None:
        """Execute the appropriate compensation for a resource record."""

        if record.resource_type == ResourceType.DB:
            self._compensate_db(action_id, record)
        elif record.resource_type == ResourceType.EMAIL:
            self._compensate_email(action_id, record)
        elif record.resource_type == ResourceType.FILE:
            self._compensate_file(action_id, record)
        elif record.resource_type == ResourceType.WEBHOOK:
            self._compensate_webhook(action_id, record)
        else:
            raise ValueError(
                f"Unknown resource type: {record.resource_type}"
            )

    def _compensate_db(
        self,
        action_id: str,
        record: ResourceRecord,
    ) -> None:
        """Roll back a DB operation using DBTransactionJournal."""

        journal_id = record.rollback_data.get("journal_id", "")
        if not journal_id:
            raise ValueError(
                f"No journal_id in rollback_data for DB record in action {action_id}"
            )

        journal = get_db_journal()
        result = journal.rollback_to(journal_id)

        if not result.success:
            errors_str = "; ".join(result.errors) if result.errors else "unknown"
            raise RuntimeError(
                f"DB rollback failed for journal {journal_id[:12]}: {errors_str}"
            )

        logger.info(
            "CoordinatedRollbackManager: DB compensation done journal=%s restored=%d",
            journal_id[:12], result.rows_restored,
        )

    def _compensate_email(
        self,
        action_id: str,
        record: ResourceRecord,
    ) -> None:
        """Log a "recall" notification for a sent email.

        Emails cannot be unsent, so we log a recall notice.
        """
        to_addr = record.rollback_data.get("to", "unknown")
        subject = record.rollback_data.get("subject", "unknown")
        message_id = record.resource_id

        logger.warning(
            "CoordinatedRollbackManager: EMAIL RECALL notification — "
            "action=%s message_id=%s to=%s subject='%s'. "
            "Note: email cannot be unsent; manual follow-up required.",
            action_id[:12], message_id, to_addr, subject,
        )

        # Persist the recall log
        def _log_recall() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS email_recall_log (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        action_id  TEXT NOT NULL,
                        message_id TEXT NOT NULL,
                        to_addr    TEXT,
                        subject    TEXT,
                        recalled_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO email_recall_log
                        (action_id, message_id, to_addr, subject, recalled_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (action_id, message_id, to_addr, subject, time.time()),
                )
                conn.commit()
            finally:
                conn.close()

        with_retry(
            _log_recall,
            max_retries=3,
            base_delay=0.5,
            label="coordinated_rollback._compensate_email",
        )

    def _compensate_file(
        self,
        action_id: str,
        record: ResourceRecord,
    ) -> None:
        """Restore a file from its backup path."""

        source = record.rollback_data.get("source", "")
        backup_path = record.rollback_data.get("backup_path", "")
        operation = record.rollback_data.get("operation", "")

        if not source:
            raise ValueError(
                f"No source path in rollback_data for FILE record in action {action_id}"
            )

        if operation == "create":
            # File was created — delete it
            def _do_delete() -> None:
                p = Path(source)
                if p.exists():
                    p.unlink()
                    logger.info(
                        "CoordinatedRollbackManager: deleted created file %s",
                        source,
                    )
                else:
                    logger.debug(
                        "CoordinatedRollbackManager: file %s already absent (create rollback)",
                        source,
                    )

            with_retry(
                _do_delete,
                max_retries=3,
                base_delay=0.5,
                label="coordinated_rollback._compensate_file(delete)",
            )
        elif operation == "delete":
            # File was deleted — restore from backup
            if not backup_path:
                raise ValueError(
                    f"No backup_path for DELETE file rollback in action {action_id}"
                )

            def _do_restore() -> None:
                bk = Path(backup_path)
                dst = Path(source)
                if bk.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(bk), str(dst))
                    logger.info(
                        "CoordinatedRollbackManager: restored deleted file %s from %s",
                        source, backup_path,
                    )
                else:
                    raise FileNotFoundError(
                        f"Backup not found at {backup_path} for file {source}"
                    )

            with_retry(
                _do_restore,
                max_retries=3,
                base_delay=0.5,
                label="coordinated_rollback._compensate_file(restore)",
            )
        elif operation == "modify":
            # File was modified — restore from backup
            if not backup_path:
                raise ValueError(
                    f"No backup_path for MODIFY file rollback in action {action_id}"
                )

            def _do_restore() -> None:
                bk = Path(backup_path)
                dst = Path(source)
                if bk.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(bk), str(dst))
                    logger.info(
                        "CoordinatedRollbackManager: restored modified file %s from %s",
                        source, backup_path,
                    )
                else:
                    raise FileNotFoundError(
                        f"Backup not found at {backup_path} for file {source}"
                    )

            with_retry(
                _do_restore,
                max_retries=3,
                base_delay=0.5,
                label="coordinated_rollback._compensate_file(modify)",
            )
        else:
            raise ValueError(
                f"Unknown file operation '{operation}' for rollback in action {action_id}"
            )

    def _compensate_webhook(
        self,
        action_id: str,
        record: ResourceRecord,
    ) -> None:
        """Send a cancellation webhook if the endpoint supports it."""

        url = record.rollback_data.get("cancellation_url", "")
        original_payload = record.rollback_data.get("payload", {})

        if not url:
            logger.warning(
                "CoordinatedRollbackManager: no cancellation URL for webhook "
                "record in action %s — skipping",
                action_id[:12],
            )
            return

        cancellation_payload = {
            "zenic_cancellation": True,
            "action_id": action_id,
            "original_payload": original_payload,
            "reason": "coordinated_rollback",
            "timestamp": time.time(),
        }

        def _send_cancellation() -> None:
            import urllib.request
            import urllib.error

            data = json.dumps(cancellation_payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    status = resp.status
                    logger.info(
                        "CoordinatedRollbackManager: cancellation webhook sent to %s "
                        "status=%d",
                        url[:50], status,
                    )
            except urllib.error.URLError as exc:
                logger.warning(
                    "CoordinatedRollbackManager: cancellation webhook to %s failed: %s",
                    url[:50], exc,
                )
                # We do NOT raise — webhook cancellation is best-effort

        with_retry(
            _send_cancellation,
            max_retries=3,
            base_delay=0.5,
            label="coordinated_rollback._compensate_webhook",
        )

    # ── Persistence helpers ──────────────────────────────────

    def _add_record(self, action_id: str, record: ResourceRecord) -> None:
        """Persist a ResourceRecord and attach it to an action."""
        with self._lock:

            def _do_add() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(
                        """
                        INSERT INTO resource_records
                            (action_id, resource_type, resource_id,
                             rollback_data, compensation_executed, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            action_id,
                            record.resource_type.value,
                            record.resource_id,
                            json.dumps(record.rollback_data, default=str),
                            1 if record.compensation_executed else 0,
                            record.created_at,
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

            with_retry(
                _do_add,
                max_retries=3,
                base_delay=0.5,
                label=f"coordinated_rollback._add_record({action_id[:12]})",
            )

    def _mark_record_compensated(
        self,
        action_id: str,
        record: ResourceRecord,
    ) -> None:
        """Mark a resource record as compensated in SQLite."""

        def _do_mark() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(
                    """
                    UPDATE resource_records
                    SET compensation_executed = 1
                    WHERE action_id = ?
                      AND resource_type = ?
                      AND resource_id = ?
                    """,
                    (
                        action_id,
                        record.resource_type.value,
                        record.resource_id,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        with_retry(
            _do_mark,
            max_retries=3,
            base_delay=0.5,
            label=f"coordinated_rollback._mark_compensated({action_id[:12]})",
        )

    def _update_action_status(
        self,
        action_id: str,
        status: ActionStatus,
    ) -> None:
        """Update the status of a coordinated action in SQLite."""

        def _do_update() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(
                    "UPDATE coordinated_actions SET status = ? WHERE action_id = ?",
                    (status.value, action_id),
                )
                conn.commit()
            finally:
                conn.close()

        with_retry(
            _do_update,
            max_retries=3,
            base_delay=0.5,
            label=f"coordinated_rollback._update_status({action_id[:12]})",
        )

    def _load_action(self, action_id: str) -> Optional[CoordinatedAction]:
        """Load a CoordinatedAction and all its records from SQLite."""

        def _do_load() -> Optional[CoordinatedAction]:
            conn = sqlite3.connect(self._db_path)
            try:
                # Load the action
                cursor = conn.execute(
                    "SELECT action_id, tenant_id, status, created_at "
                    "FROM coordinated_actions WHERE action_id = ?",
                    (action_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None

                action = CoordinatedAction(
                    action_id=row[0],
                    tenant_id=row[1],
                    status=ActionStatus(row[2]),
                    created_at=row[3],
                )

                # Load all records for this action
                cursor2 = conn.execute(
                    """
                    SELECT resource_type, resource_id, rollback_data,
                           compensation_executed, created_at
                    FROM resource_records
                    WHERE action_id = ?
                    ORDER BY created_at ASC
                    """,
                    (action_id,),
                )
                for rec_row in cursor2.fetchall():
                    record = ResourceRecord(
                        resource_type=ResourceType(rec_row[0]),
                        resource_id=rec_row[1],
                        rollback_data=json.loads(rec_row[2]) if rec_row[2] else {},
                        compensation_executed=bool(rec_row[3]),
                        created_at=rec_row[4],
                    )
                    action.records.append(record)

                return action
            finally:
                conn.close()

        return with_retry(
            _do_load,
            max_retries=3,
            base_delay=0.5,
            label=f"coordinated_rollback._load_action({action_id[:12]})",
        )


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
