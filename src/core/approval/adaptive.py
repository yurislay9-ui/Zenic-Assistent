"""
Zenic-Agents Asistente - Adaptive Approval Engine (Phase C3)

Learns from past approval decisions to auto-approve repetitive safe actions.
When a user consistently approves the same type of action, the engine
automatically approves future occurrences after a configurable threshold
of consecutive approvals.

Safety guards:
  - Never auto-approve CRITICAL priority actions
  - Never auto-approve FINANCIAL actions (payment/financial)
  - Rejection resets the consecutive approval counter to zero

Persistence: SQLite with retry logic.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Action categories that are NEVER auto-approved
_FINANCIAL_KEYWORDS = ("payment", "financial", "refund", "invoice_pay")
_MAX_RETRIES = 3
_RETRY_DELAY = 0.1  # seconds between retries


@dataclass
class AdaptiveApprovalRecord:
    """Tracks approval history for a user+action_type+config_hash combination."""

    record_id: str = ""
    user_id: int = 0
    action_type: str = ""
    action_config_hash: str = ""
    consecutive_approvals: int = 0
    last_auto_approved: str = ""
    total_auto_approvals: int = 0
    total_manual_approvals: int = 0
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.record_id:
            self.record_id = f"adar-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def should_auto_approve(self, threshold: int = 5) -> bool:
        """Return True if consecutive_approvals >= threshold."""
        return self.consecutive_approvals >= threshold

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "record_id": self.record_id,
            "user_id": self.user_id,
            "action_type": self.action_type,
            "action_config_hash": self.action_config_hash,
            "consecutive_approvals": self.consecutive_approvals,
            "last_auto_approved": self.last_auto_approved,
            "total_auto_approvals": self.total_auto_approvals,
            "total_manual_approvals": self.total_manual_approvals,
            "created_at": self.created_at,
        }


def _hash_config(action_config: Dict[str, Any]) -> str:
    """Produce a stable hash of an action config dict."""
    canonical = json.dumps(action_config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class AdaptiveApprovalEngine:
    """Learns from past approvals to auto-approve repetitive safe actions.

    Tracks consecutive approvals per user/action_type/config_hash.
    When the count exceeds *auto_approve_threshold*, future identical
    requests can be automatically approved (subject to safety guards).
    """

    def __init__(
        self,
        db_path: str = "adaptive_approval.sqlite",
        auto_approve_threshold: int = 5,
    ) -> None:
        self._db_path = db_path
        self._auto_approve_threshold = auto_approve_threshold
        self._lock = threading.RLock()
        self._init_db()

    # ── DB Initialisation ──────────────────────────────────

    def _init_db(self) -> None:
        """Create the adaptive_approval table if it does not exist."""
        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS adaptive_approval_records (
                    record_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    action_config_hash TEXT NOT NULL,
                    consecutive_approvals INTEGER NOT NULL DEFAULT 0,
                    last_auto_approved TEXT NOT NULL DEFAULT '',
                    total_auto_approvals INTEGER NOT NULL DEFAULT 0,
                    total_manual_approvals INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE UNIQUE INDEX IF NOT EXISTS idx_adaptive_user_action_hash
                ON adaptive_approval_records(user_id, action_type, action_config_hash)
            """)
            conn.commit()
            conn.close()

        self._with_retry(_do_init)

    # ── Core Operations ────────────────────────────────────

    def record_approval(
        self,
        user_id: int,
        action_type: str,
        action_config: Dict[str, Any],
        was_auto: bool = False,
    ) -> AdaptiveApprovalRecord:
        """Record that an approval was granted.

        Finds or creates a record for user+action_type+config_hash.
        Increments consecutive_approvals; resets to 0 on rejection.
        If consecutive_approvals >= threshold, marks as auto-approvable.
        """
        config_hash = _hash_config(action_config)
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            record = self._find_record(user_id, action_type, config_hash)

            if record is None:
                record = AdaptiveApprovalRecord(
                    user_id=user_id,
                    action_type=action_type,
                    action_config_hash=config_hash,
                    consecutive_approvals=1,
                )
                self._persist_record(record, insert=True)
            else:
                record.consecutive_approvals += 1
                if was_auto:
                    record.total_auto_approvals += 1
                    record.last_auto_approved = now
                else:
                    record.total_manual_approvals += 1
                self._persist_record(record, insert=False)

        logger.info(
            "AdaptiveApproval: Recorded approval for user=%d action='%s' "
            "consecutive=%d was_auto=%s",
            user_id, action_type, record.consecutive_approvals, was_auto,
        )
        return record

    def record_rejection(
        self,
        user_id: int,
        action_type: str,
        action_config: Dict[str, Any],
        reason: str = "",
    ) -> None:
        """Record a rejection — resets consecutive_approvals to 0."""
        config_hash = _hash_config(action_config)

        with self._lock:
            record = self._find_record(user_id, action_type, config_hash)
            if record is not None:
                record.consecutive_approvals = 0
                self._persist_record(record, insert=False)
                logger.info(
                    "AdaptiveApproval: Rejection reset consecutive_approvals "
                    "for user=%d action='%s' reason='%s'",
                    user_id, action_type, reason[:80],
                )

    def check_auto_approve(
        self,
        user_id: int,
        action_type: str,
        action_config: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Check whether the given action should be auto-approved.

        Returns (should_auto_approve, reason).
        Safety guards:
          - Never auto-approve CRITICAL priority actions
          - Never auto-approve FINANCIAL actions
        """
        # Safety guard: financial actions
        action_lower = action_type.lower()
        for kw in _FINANCIAL_KEYWORDS:
            if kw in action_lower:
                return (False, f"Action type '{action_type}' is financial — never auto-approved")

        # Safety guard: critical priority (check config)
        priority = action_config.get("priority", "").lower()
        if priority == "critical":
            return (False, "CRITICAL priority actions are never auto-approved")

        config_hash = _hash_config(action_config)
        record = self._find_record(user_id, action_type, config_hash)

        if record is None:
            return (False, "No approval history for this action pattern")

        if record.should_auto_approve(self._auto_approve_threshold):
            return (
                True,
                f"Auto-approved: {record.consecutive_approvals} consecutive approvals "
                f"(threshold={self._auto_approve_threshold})",
            )

        return (
            False,
            f"Only {record.consecutive_approvals}/{self._auto_approve_threshold} "
            f"consecutive approvals",
        )

    # ── Query Methods ──────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics across all adaptive records."""
        def _do_query() -> Dict[str, Any]:
            conn = sqlite3.connect(self._db_path)
            try:
                total = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT COUNT(*) FROM adaptive_approval_records"
                ).fetchone()[0]
                auto_approved = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT SUM(total_auto_approvals) FROM adaptive_approval_records"
                ).fetchone()[0] or 0
                avg_consecutive_row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT AVG(consecutive_approvals) FROM adaptive_approval_records"
                ).fetchone()[0]
                avg_consecutive = round(avg_consecutive_row, 2) if avg_consecutive_row is not None else 0.0
            finally:
                conn.close()
            return {
                "total_records": total,
                "total_auto_approved": auto_approved,
                "avg_consecutive": avg_consecutive,
                "auto_approve_threshold": self._auto_approve_threshold,
            }

        return self._with_retry(_do_query, fallback={})

    def reset_user(self, user_id: int) -> None:
        """Reset (delete) all adaptive records for a user."""
        def _do_reset() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "DELETE FROM adaptive_approval_records WHERE user_id = ?",
                (user_id,),
            )
            conn.commit()
            conn.close()

        with self._lock:
            self._with_retry(_do_reset)
        logger.info("AdaptiveApproval: Reset all records for user=%d", user_id)

    # ── Private Helpers ────────────────────────────────────

    def _find_record(
        self, user_id: int, action_type: str, config_hash: str,
    ) -> Optional[AdaptiveApprovalRecord]:
        """Look up an existing adaptive record."""
        def _do_find() -> Optional[AdaptiveApprovalRecord]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """SELECT * FROM adaptive_approval_records
                   WHERE user_id = ? AND action_type = ? AND action_config_hash = ?""",
                (user_id, action_type, config_hash),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return AdaptiveApprovalRecord(
                record_id=row["record_id"],
                user_id=row["user_id"],
                action_type=row["action_type"],
                action_config_hash=row["action_config_hash"],
                consecutive_approvals=row["consecutive_approvals"],
                last_auto_approved=row["last_auto_approved"] or "",
                total_auto_approvals=row["total_auto_approvals"],
                total_manual_approvals=row["total_manual_approvals"],
                created_at=row["created_at"],
            )

        return self._with_retry(_do_find, fallback=None)

    def _persist_record(self, record: AdaptiveApprovalRecord, *, insert: bool) -> None:
        """Insert or update a record in the database."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            if insert:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT INTO adaptive_approval_records
                       (record_id, user_id, action_type, action_config_hash,
                        consecutive_approvals, last_auto_approved,
                        total_auto_approvals, total_manual_approvals, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.record_id, record.user_id, record.action_type,
                        record.action_config_hash, record.consecutive_approvals,
                        record.last_auto_approved, record.total_auto_approvals,
                        record.total_manual_approvals, record.created_at,
                    ),
                )
            else:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """UPDATE adaptive_approval_records SET
                       consecutive_approvals=?, last_auto_approved=?,
                       total_auto_approvals=?, total_manual_approvals=?
                       WHERE record_id=?""",
                    (
                        record.consecutive_approvals, record.last_auto_approved,
                        record.total_auto_approvals, record.total_manual_approvals,
                        record.record_id,
                    ),
                )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)

    def _with_retry(
        self,
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
                    "AdaptiveApproval: DB retry %d/%d — %s", attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    time.sleep(_RETRY_DELAY * attempt)
            except Exception as exc:
                last_exc = exc
                logger.error("AdaptiveApproval: DB error — %s", exc)
                break
        logger.error(
            "AdaptiveApproval: All retries exhausted — %s", last_exc,
        )
        return fallback


# ── Singleton ─────────────────────────────────────────────

_adaptive_instance: Optional[AdaptiveApprovalEngine] = None
_adaptive_lock = threading.Lock()


def get_adaptive_approval(
    db_path: str = "adaptive_approval.sqlite",
    auto_approve_threshold: int = 5,
) -> AdaptiveApprovalEngine:
    """Get or create the global AdaptiveApprovalEngine instance."""
    global _adaptive_instance
    with _adaptive_lock:
        if _adaptive_instance is None:
            _adaptive_instance = AdaptiveApprovalEngine(
                db_path=db_path,
                auto_approve_threshold=auto_approve_threshold,
            )
        return _adaptive_instance


def reset_adaptive_approval() -> None:
    """Reset the global AdaptiveApprovalEngine (for testing)."""
    global _adaptive_instance
    _adaptive_instance = None


__all__ = [
    "AdaptiveApprovalRecord",
    "AdaptiveApprovalEngine",
    "get_adaptive_approval",
    "reset_adaptive_approval",
]
