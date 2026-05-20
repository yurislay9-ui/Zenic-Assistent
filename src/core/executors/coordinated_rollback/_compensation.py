"""
ZENIC-AGENTS - Coordinated Rollback Compensation Executors

Handles the actual rollback logic for each resource type:
  DB, Email, File, Webhook.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from src.core.shared.retry import with_retry
from src.core.executors.db_journal import DBTransactionJournal, get_db_journal
from src.core.executors.coordinated_rollback._types import (
    ResourceType,
    ResourceRecord,
)

logger = logging.getLogger(__name__)


def _validate_url(url: str, allowed_schemes: tuple = ("http", "https")) -> str:
    """Validate URL to prevent SSRF attacks."""
    parsed = urlparse(url)
    if parsed.scheme not in allowed_schemes:
        raise ValueError(f"URL scheme '{parsed.scheme}' not allowed. Use: {allowed_schemes}")
    if not parsed.hostname:
        raise ValueError("URL must have a hostname")
    try:
        ip = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        pass  # hostname is not an IP, that's OK
    else:
        if ip.is_private or ip.is_loopback or ip.is_reserved:
            raise ValueError(f"Access to internal IPs is not allowed: {parsed.hostname}")
    return url


def execute_compensation(
    action_id: str,
    record: ResourceRecord,
    db_path: str,
) -> None:
    """Dispatch to the appropriate compensation executor for a resource record.

    Args:
        action_id: The coordinated action ID.
        record: The resource record to compensate.
        db_path: Path to the SQLite database for persistence.
    """
    if record.resource_type == ResourceType.DB:
        _compensate_db(action_id, record)
    elif record.resource_type == ResourceType.EMAIL:
        _compensate_email(action_id, record, db_path)
    elif record.resource_type == ResourceType.FILE:
        _compensate_file(action_id, record)
    elif record.resource_type == ResourceType.WEBHOOK:
        _compensate_webhook(action_id, record)
    else:
        raise ValueError(f"Unknown resource type: {record.resource_type}")


def _compensate_db(action_id: str, record: ResourceRecord) -> None:
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


def _compensate_email(action_id: str, record: ResourceRecord, db_path: str) -> None:
    """Log a 'recall' notification for a sent email.

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
        conn = sqlite3.connect(db_path)
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


def _compensate_file(action_id: str, record: ResourceRecord) -> None:
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
    elif operation in ("delete", "modify"):
        # File was deleted or modified — restore from backup
        if not backup_path:
            raise ValueError(
                f"No backup_path for {operation.upper()} file rollback in action {action_id}"
            )

        def _do_restore() -> None:
            bk = Path(backup_path)
            dst = Path(source)
            if bk.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(bk), str(dst))
                logger.info(
                    "CoordinatedRollbackManager: restored %s file %s from %s",
                    operation, source, backup_path,
                )
            else:
                raise FileNotFoundError(
                    f"Backup not found at {backup_path} for file {source}"
                )

        with_retry(
            _do_restore,
            max_retries=3,
            base_delay=0.5,
            label=f"coordinated_rollback._compensate_file({operation})",
        )
    else:
        raise ValueError(
            f"Unknown file operation '{operation}' for rollback in action {action_id}"
        )


def _compensate_webhook(action_id: str, record: ResourceRecord) -> None:
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

        validated_url = _validate_url(url)
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
