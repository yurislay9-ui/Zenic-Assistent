"""
Zenic-Agents Asistente - Evidence Attached to Approvals (Phase 5)

Manages evidence records attached to approval requests. Each piece of
evidence is immutable (append-only) and SHA-256 hashed for integrity.

Evidence types:
  - SCREENSHOT: Visual capture of the state
  - LOG: Log entries relevant to the decision
  - DATA_SNAPSHOT: Point-in-time data extract
  - POLICY_RESULT: Output from the policy engine
  - AUDIT_RECORD: Reference to an audit trail entry
  - CUSTOM: User-defined evidence type

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
from enum import Enum
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1


class EvidenceType(str, Enum):
    """Type of evidence attached to an approval."""
    SCREENSHOT = "screenshot"
    LOG = "log"
    DATA_SNAPSHOT = "data_snapshot"
    POLICY_RESULT = "policy_result"
    AUDIT_RECORD = "audit_record"
    CUSTOM = "custom"


@dataclass
class ApprovalEvidence:
    """A piece of evidence attached to an approval request.

    Evidence is immutable: once created, the content cannot be modified.
    The content_hash provides a SHA-256 fingerprint of the content dict
    for tamper detection.
    """

    evidence_id: str = ""
    evidence_type: EvidenceType = EvidenceType.CUSTOM
    content: Dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    source: str = ""
    timestamp: str = ""
    request_id: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_id:
            self.evidence_id = f"ev-{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.content_hash and self.content:
            self.content_hash = _hash_content(self.content)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type.value,
            "content": self.content,
            "content_hash": self.content_hash,
            "source": self.source,
            "timestamp": self.timestamp,
            "request_id": self.request_id,
        }


def _hash_content(content: Dict[str, Any]) -> str:
    """Compute a SHA-256 hash of the content dict."""
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class EvidenceManager:
    """Manages evidence records attached to approval requests.

    Evidence is append-only — it cannot be modified after creation.
    Only admin-level deletion is supported.
    """

    def __init__(self, db_path: str = "evidence.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    # ── DB Initialisation ──────────────────────────────────

    def _init_db(self) -> None:
        """Create the evidence table if it does not exist."""
        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS approval_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    evidence_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    timestamp TEXT NOT NULL,
                    request_id TEXT NOT NULL
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_evidence_request
                ON approval_evidence(request_id, evidence_type)
            """)
            conn.commit()
            conn.close()

        self._with_retry(_do_init)

    # ── Core Operations ────────────────────────────────────

    def attach_evidence(
        self,
        request_id: str,
        evidence_type: Union[EvidenceType, str],
        content: Dict[str, Any],
        source: str = "",
    ) -> ApprovalEvidence:
        """Attach a new piece of evidence to an approval request.

        Args:
            request_id: The approval request this evidence belongs to.
            evidence_type: The type of evidence being attached (enum or string).
            content: Arbitrary key-value data constituting the evidence.
            source: Identifier of the system or user providing the evidence.

        Returns:
            The created ApprovalEvidence with computed content_hash.
        """
        if not request_id:
            raise ValueError("request_id is required")
        if not content:
            raise ValueError("content is required for evidence")

        # Coerce string to EvidenceType enum
        if isinstance(evidence_type, str):
            evidence_type = EvidenceType(evidence_type)

        evidence = ApprovalEvidence(
            evidence_type=evidence_type,
            content=content,
            source=source,
            request_id=request_id,
        )

        with self._lock:
            self._persist_evidence(evidence, insert=True)

        # Record audit event
        self._record_audit_event(request_id, evidence)

        logger.info(
            "EvidenceManager: Attached %s evidence %s to request %s",
            evidence_type.value, evidence.evidence_id, request_id,
        )
        return evidence

    def get_evidence(self, request_id: str) -> List[ApprovalEvidence]:
        """Get all evidence attached to a request."""
        def _do_query() -> List[ApprovalEvidence]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """SELECT * FROM approval_evidence
                   WHERE request_id = ?
                   ORDER BY timestamp ASC""",
                (request_id,),
            ).fetchall()
            conn.close()
            return [self._row_to_evidence(r) for r in rows]

        return self._with_retry(_do_query, fallback=[])

    def verify_evidence_integrity(self, evidence_id: str) -> bool:
        """Verify the SHA-256 integrity of an evidence record.

        Recomputes the hash from stored content and compares with the
        stored content_hash.
        """
        evidence = self._find_evidence(evidence_id)
        if evidence is None:
            logger.warning("EvidenceManager: Evidence %s not found for integrity check", evidence_id)
            return False

        recomputed = _hash_content(evidence.content)
        return recomputed == evidence.content_hash

    def get_evidence_by_type(
        self, request_id: str, evidence_type: Union[EvidenceType, str],
    ) -> List[ApprovalEvidence]:
        """Get evidence of a specific type for a request."""
        if isinstance(evidence_type, str):
            evidence_type = EvidenceType(evidence_type)
        def _do_query() -> List[ApprovalEvidence]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """SELECT * FROM approval_evidence
                   WHERE request_id = ? AND evidence_type = ?
                   ORDER BY timestamp ASC""",
                (request_id, evidence_type.value),
            ).fetchall()
            conn.close()
            return [self._row_to_evidence(r) for r in rows]

        return self._with_retry(_do_query, fallback=[])

    def delete_evidence(self, evidence_id: str) -> bool:
        """Delete an evidence record (admin-level operation).

        Returns True if the record was found and deleted.
        """
        with self._lock:
            evidence = self._find_evidence(evidence_id)
            if evidence is None:
                logger.warning("EvidenceManager: Evidence %s not found for deletion", evidence_id)
                return False

            def _do_delete() -> None:
                conn = sqlite3.connect(self._db_path)
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "DELETE FROM approval_evidence WHERE evidence_id = ?",
                    (evidence_id,),
                )
                conn.commit()
                conn.close()

            self._with_retry(_do_delete)

        logger.info("EvidenceManager: Deleted evidence %s", evidence_id)
        return True

    # ── Private Helpers ────────────────────────────────────

    def _find_evidence(self, evidence_id: str) -> Optional[ApprovalEvidence]:
        """Find a single evidence record by ID."""
        def _do_find() -> Optional[ApprovalEvidence]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM approval_evidence WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return self._row_to_evidence(row)

        return self._with_retry(_do_find, fallback=None)

    def _persist_evidence(self, evidence: ApprovalEvidence, *, insert: bool) -> None:
        """Insert or update an evidence record in the database."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            if insert:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT INTO approval_evidence
                       (evidence_id, evidence_type, content, content_hash,
                        source, timestamp, request_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        evidence.evidence_id,
                        evidence.evidence_type.value,
                        json.dumps(evidence.content),
                        evidence.content_hash,
                        evidence.source,
                        evidence.timestamp,
                        evidence.request_id,
                    ),
                )
            else:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """UPDATE approval_evidence SET
                       content=?, content_hash=?, source=?
                       WHERE evidence_id=?""",
                    (
                        json.dumps(evidence.content),
                        evidence.content_hash,
                        evidence.source,
                        evidence.evidence_id,
                    ),
                )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)

    @staticmethod
    def _row_to_evidence(row: sqlite3.Row) -> ApprovalEvidence:
        """Convert a database row to an ApprovalEvidence."""
        return ApprovalEvidence(
            evidence_id=row["evidence_id"],
            evidence_type=EvidenceType(row["evidence_type"]),
            content=json.loads(row["content"] or "{}"),
            content_hash=row["content_hash"],
            source=row["source"] or "",
            timestamp=row["timestamp"],
            request_id=row["request_id"],
        )

    def _record_audit_event(
        self, request_id: str, evidence: ApprovalEvidence,
    ) -> None:
        """Record an EVIDENCE_ATTACHED event in the audit merkle trail."""
        try:
            from .audit_merkle import get_approval_audit_merkle
            audit = get_approval_audit_merkle()
            audit.record_event(
                request_id=request_id,
                event_type="EVIDENCE_ATTACHED",
                actor_id=evidence.source or "system",
                actor_name=evidence.source or "system",
                details={
                    "evidence_id": evidence.evidence_id,
                    "evidence_type": evidence.evidence_type.value,
                    "content_hash": evidence.content_hash,
                },
            )
        except Exception as exc:
            logger.debug("EvidenceManager: audit event recording failed: %s", exc)

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
                    "EvidenceManager: DB retry %d/%d — %s", attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    time.sleep(_RETRY_DELAY * attempt)
            except Exception as exc:
                last_exc = exc
                logger.error("EvidenceManager: DB error — %s", exc)
                break
        logger.error("EvidenceManager: All retries exhausted — %s", last_exc)
        return fallback


# ── Singleton ─────────────────────────────────────────────

_evidence_instance: Optional[EvidenceManager] = None
_evidence_lock = threading.Lock()


def get_evidence_manager(db_path: str = "evidence.sqlite") -> EvidenceManager:
    """Get or create the global EvidenceManager instance."""
    global _evidence_instance
    with _evidence_lock:
        if _evidence_instance is None:
            _evidence_instance = EvidenceManager(db_path=db_path)
        return _evidence_instance


def reset_evidence_manager() -> None:
    """Reset the global EvidenceManager (for testing)."""
    global _evidence_instance
    _evidence_instance = None


__all__ = [
    "EvidenceType",
    "ApprovalEvidence",
    "EvidenceManager",
    "get_evidence_manager",
    "reset_evidence_manager",
]
