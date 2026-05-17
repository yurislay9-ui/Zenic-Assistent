"""
Zenic-Agents Asistente - Mandatory Justification (Phase 5)

Ensures that every approval or rejection is accompanied by a mandatory
justification. The justification requirements vary by priority level:

  - CRITICAL/EMERGENCY: All fields required, min_length=50
  - HIGH: risk_acknowledgment + compliance_check required, min_length=30
  - MEDIUM: risk_acknowledgment required, min_length=20
  - LOW: just reason, min_length=10

Justifications are immutable after creation (SHA-256 hashed).

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
from typing import Any, Dict, List, Optional, Tuple, Union

from .chain import ApprovalPriority

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1


@dataclass
class JustificationRequirement:
    """Requirements for a justification based on priority level."""

    min_length: int = 20
    require_risk_acknowledgment: bool = False
    require_compliance_check: bool = False
    require_business_justification: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "min_length": self.min_length,
            "require_risk_acknowledgment": self.require_risk_acknowledgment,
            "require_compliance_check": self.require_compliance_check,
            "require_business_justification": self.require_business_justification,
        }


@dataclass
class ApprovalJustification:
    """A justification provided for approving or rejecting a request.

    Justifications are immutable after creation.
    The content_hash provides a SHA-256 fingerprint for tamper detection.
    """

    justification_id: str = ""
    request_id: str = ""
    reason: str = ""
    risk_acknowledgment: bool = False
    compliance_check: bool = False
    business_justification: str = ""
    created_by: str = ""
    created_at: str = ""
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.justification_id:
            self.justification_id = f"jus-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.content_hash:
            self.content_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute SHA-256 hash of the justification content."""
        payload = json.dumps({
            "request_id": self.request_id,
            "reason": self.reason,
            "risk_acknowledgment": self.risk_acknowledgment,
            "compliance_check": self.compliance_check,
            "business_justification": self.business_justification,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "justification_id": self.justification_id,
            "request_id": self.request_id,
            "reason": self.reason,
            "risk_acknowledgment": self.risk_acknowledgment,
            "compliance_check": self.compliance_check,
            "business_justification": self.business_justification,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "content_hash": self.content_hash,
        }


class JustificationManager:
    """Manages mandatory justifications for approval decisions.

    Justifications are MANDATORY for both approve and reject.
    Cannot approve/reject without meeting justification requirements.
    """

    def __init__(self, db_path: str = "justification.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    # ── DB Initialisation ──────────────────────────────────

    def _init_db(self) -> None:
        """Create the justifications table if it does not exist."""
        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS justifications (
                    justification_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    risk_acknowledgment INTEGER NOT NULL DEFAULT 0,
                    compliance_check INTEGER NOT NULL DEFAULT 0,
                    business_justification TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE UNIQUE INDEX IF NOT EXISTS idx_justification_request
                ON justifications(request_id)
            """)
            conn.commit()
            conn.close()

        self._with_retry(_do_init)

    # ── Core Operations ────────────────────────────────────

    def validate_justification(
        self,
        justification: Union[ApprovalJustification, str],
        requirement: JustificationRequirement,
    ) -> Tuple[bool, List[str]]:
        """Validate a justification against requirements.

        Args:
            justification: An ApprovalJustification object or a reason string.
            requirement: The requirements to validate against.

        Returns:
            Tuple of (is_valid, list_of_errors).
        """
        errors: List[str] = []

        # Normalize: if string, create a minimal ApprovalJustification for validation
        if isinstance(justification, str):
            reason = justification.strip()
            # Only check reason length when string is passed
            if len(reason) < requirement.min_length:
                errors.append(
                    f"Reason must be at least {requirement.min_length} characters "
                    f"(got {len(reason)})"
                )
            if requirement.require_risk_acknowledgment:
                errors.append("Risk acknowledgment is required")
            if requirement.require_compliance_check:
                errors.append("Compliance check is required")
            if requirement.require_business_justification:
                errors.append("Business justification is required")
            return (len(errors) == 0, errors)

        # Full object validation
        # Check reason length
        if len(justification.reason.strip()) < requirement.min_length:
            errors.append(
                f"Reason must be at least {requirement.min_length} characters "
                f"(got {len(justification.reason.strip())})"
            )

        # Check risk acknowledgment
        if requirement.require_risk_acknowledgment and not justification.risk_acknowledgment:
            errors.append("Risk acknowledgment is required")

        # Check compliance check
        if requirement.require_compliance_check and not justification.compliance_check:
            errors.append("Compliance check is required")

        # Check business justification
        if requirement.require_business_justification and not justification.business_justification.strip():
            errors.append("Business justification is required")

        return (len(errors) == 0, errors)

    def create_justification(
        self,
        request_id: str,
        reason: str,
        risk_acknowledgment: bool = False,
        compliance_check: bool = False,
        business_justification: str = "",
        created_by: str = "",
        requirement: Optional[JustificationRequirement] = None,
    ) -> ApprovalJustification:
        """Create a new justification for a request.

        Auto-validates and raises ValueError if validation fails.
        If no requirement is provided, derives one from the request's priority.
        """
        if not request_id:
            raise ValueError("request_id is required")
        if not reason:
            raise ValueError("reason is required for justification")

        # Determine requirement if not provided
        if requirement is None:
            requirement = self.get_justification_requirement(request_id)

        justification = ApprovalJustification(
            request_id=request_id,
            reason=reason,
            risk_acknowledgment=risk_acknowledgment,
            compliance_check=compliance_check,
            business_justification=business_justification,
            created_by=created_by,
        )

        # Validate
        is_valid, errors = self.validate_justification(justification, requirement)
        if not is_valid:
            raise ValueError(
                "Justification validation failed: " + "; ".join(errors)
            )

        with self._lock:
            self._persist_justification(justification, insert=True)

        # Record audit event
        self._record_audit_event(request_id, justification)

        logger.info(
            "JustificationManager: Created justification %s for request %s",
            justification.justification_id, request_id,
        )
        return justification

    def get_justification(self, request_id: str) -> Optional[ApprovalJustification]:
        """Get the justification for a request (one per request)."""
        def _do_find() -> Optional[ApprovalJustification]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM justifications WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return self._row_to_justification(row)

        return self._with_retry(_do_find, fallback=None)

    def get_justification_requirement(
        self, request_id: str,
    ) -> JustificationRequirement:
        """Return the justification requirements based on request priority.

        Priority mapping:
          - CRITICAL/EMERGENCY: all required, min_length=50
          - HIGH: risk + compliance required, min_length=30
          - MEDIUM: risk required, min_length=20
          - LOW: just reason, min_length=10
        """
        priority = self._get_request_priority(request_id)

        if priority in (ApprovalPriority.CRITICAL,):
            return JustificationRequirement(
                min_length=50,
                require_risk_acknowledgment=True,
                require_compliance_check=True,
                require_business_justification=True,
            )
        if priority == ApprovalPriority.HIGH:
            return JustificationRequirement(
                min_length=30,
                require_risk_acknowledgment=True,
                require_compliance_check=True,
                require_business_justification=False,
            )
        if priority == ApprovalPriority.NORMAL:
            return JustificationRequirement(
                min_length=20,
                require_risk_acknowledgment=True,
                require_compliance_check=False,
                require_business_justification=False,
            )
        # LOW or unknown
        return JustificationRequirement(
            min_length=10,
            require_risk_acknowledgment=False,
            require_compliance_check=False,
            require_business_justification=False,
        )

    def verify_justification_integrity(self, justification_id: str) -> bool:
        """Verify the SHA-256 integrity of a justification record."""
        justification = self._find_by_id(justification_id)
        if justification is None:
            logger.warning(
                "JustificationManager: Justification %s not found for integrity check",
                justification_id,
            )
            return False

        recomputed = justification._compute_hash()
        return recomputed == justification.content_hash

    # ── Private Helpers ────────────────────────────────────

    def _get_request_priority(self, request_id: str) -> ApprovalPriority:
        """Look up the priority of a request from the approval chain."""
        try:
            from .chain import get_approval_chain
            chain = get_approval_chain()
            request = chain.get_request(request_id)
            if request is not None:
                return request.priority
        except Exception as exc:
            logger.debug("JustificationManager: could not get request priority: %s", exc)
        return ApprovalPriority.NORMAL

    def _find_by_id(self, justification_id: str) -> Optional[ApprovalJustification]:
        """Find a justification by its ID."""
        def _do_find() -> Optional[ApprovalJustification]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM justifications WHERE justification_id = ?",
                (justification_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return self._row_to_justification(row)

        return self._with_retry(_do_find, fallback=None)

    def _persist_justification(
        self, justification: ApprovalJustification, *, insert: bool,
    ) -> None:
        """Insert or update a justification in the database."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            if insert:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT INTO justifications
                       (justification_id, request_id, reason,
                        risk_acknowledgment, compliance_check,
                        business_justification, created_by,
                        created_at, content_hash)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        justification.justification_id,
                        justification.request_id,
                        justification.reason,
                        int(justification.risk_acknowledgment),
                        int(justification.compliance_check),
                        justification.business_justification,
                        justification.created_by,
                        justification.created_at,
                        justification.content_hash,
                    ),
                )
            else:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """UPDATE justifications SET
                       reason=?, risk_acknowledgment=?, compliance_check=?,
                       business_justification=?, created_by=?, content_hash=?
                       WHERE justification_id=?""",
                    (
                        justification.reason,
                        int(justification.risk_acknowledgment),
                        int(justification.compliance_check),
                        justification.business_justification,
                        justification.created_by,
                        justification.content_hash,
                        justification.justification_id,
                    ),
                )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)

    @staticmethod
    def _row_to_justification(row: sqlite3.Row) -> ApprovalJustification:
        """Convert a database row to an ApprovalJustification."""
        return ApprovalJustification(
            justification_id=row["justification_id"],
            request_id=row["request_id"],
            reason=row["reason"],
            risk_acknowledgment=bool(row["risk_acknowledgment"]),
            compliance_check=bool(row["compliance_check"]),
            business_justification=row["business_justification"] or "",
            created_by=row["created_by"] or "",
            created_at=row["created_at"],
            content_hash=row["content_hash"],
        )

    def _record_audit_event(
        self, request_id: str, justification: ApprovalJustification,
    ) -> None:
        """Record a JUSTIFICATION_PROVIDED event in the audit merkle trail."""
        try:
            from .audit_merkle import get_approval_audit_merkle
            audit = get_approval_audit_merkle()
            audit.record_event(
                request_id=request_id,
                event_type="JUSTIFICATION_PROVIDED",
                actor_id=justification.created_by or "system",
                actor_name=justification.created_by or "system",
                details={
                    "justification_id": justification.justification_id,
                    "content_hash": justification.content_hash,
                },
            )
        except Exception as exc:
            logger.debug("JustificationManager: audit event recording failed: %s", exc)

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
                    "JustificationManager: DB retry %d/%d — %s",
                    attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    time.sleep(_RETRY_DELAY * attempt)
            except Exception as exc:
                last_exc = exc
                logger.error("JustificationManager: DB error — %s", exc)
                break
        logger.error("JustificationManager: All retries exhausted — %s", last_exc)
        return fallback


# ── Singleton ─────────────────────────────────────────────

_justification_instance: Optional[JustificationManager] = None
_justification_lock = threading.Lock()


def get_justification_manager(
    db_path: str = "justification.sqlite",
) -> JustificationManager:
    """Get or create the global JustificationManager instance."""
    global _justification_instance
    with _justification_lock:
        if _justification_instance is None:
            _justification_instance = JustificationManager(db_path=db_path)
        return _justification_instance


def reset_justification_manager() -> None:
    """Reset the global JustificationManager (for testing)."""
    global _justification_instance
    _justification_instance = None


__all__ = [
    "JustificationRequirement",
    "ApprovalJustification",
    "JustificationManager",
    "get_justification_manager",
    "reset_justification_manager",
]
