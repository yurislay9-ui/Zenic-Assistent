"""
coordinated_rollback._mixin_compensation — Compensation executors mixin.
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from src.core.shared.retry import with_retry
from src.core.executors.db_journal import get_db_journal
from src.core.executors.coordinated_rollback._types import ResourceType
from src.core.executors.coordinated_rollback._helpers import validate_url

if TYPE_CHECKING:
    from src.core.executors.coordinated_rollback._types import ResourceRecord

logger = logging.getLogger(__name__)


class CompensationMixin:
    """Mixin providing compensation (rollback) executors for each resource type."""

    # These attributes are provided by the main class; declared for type checkers.
    _db_path: str
    _lock: object

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
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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

            validated_url = validate_url(url)
            data = json.dumps(cancellation_payload).encode("utf-8")
            req = urllib.request.Request(
                validated_url,
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
