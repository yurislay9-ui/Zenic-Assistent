"""
Zenic-Agents Asistente - Audit Trail in Merkle Ledger (Phase 5)

Cryptographic audit trail for all Human-in-the-Loop events. Every
HITL event is recorded in a hash-chained Merkle structure that provides
tamper-evident integrity verification.

Chain structure:
  - Each record has a content_hash = SHA-256(record data + previous_hash)
  - The first record chains to GENESIS_HASH = "0" * 64
  - Merkle proofs can be generated for any individual record

Event types:
  EVIDENCE_ATTACHED, JUSTIFICATION_PROVIDED, APPROVAL_REQUESTED,
  APPROVAL_APPROVED, APPROVAL_REJECTED, DELEGATION_CREATED,
  ESCALATION_TRIGGERED, ROLLBACK_EXECUTED, EXPIRY_REVERTED,
  UNDO_EXECUTED

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
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1

GENESIS_HASH = "0" * 64


class AuditEventType(str, Enum):
    """Types of audit events in the HITL system."""
    EVIDENCE_ATTACHED = "EVIDENCE_ATTACHED"
    JUSTIFICATION_PROVIDED = "JUSTIFICATION_PROVIDED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_APPROVED = "APPROVAL_APPROVED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    DELEGATION_CREATED = "DELEGATION_CREATED"
    ESCALATION_TRIGGERED = "ESCALATION_TRIGGERED"
    ROLLBACK_EXECUTED = "ROLLBACK_EXECUTED"
    EXPIRY_REVERTED = "EXPIRY_REVERTED"
    UNDO_EXECUTED = "UNDO_EXECUTED"


@dataclass
class AuditRecord:
    """A single record in the audit Merkle chain.

    Each record is hash-chained to its predecessor, creating
    a tamper-evident append-only log.
    """

    record_id: str = ""
    request_id: str = ""
    event_type: AuditEventType = AuditEventType.APPROVAL_REQUESTED
    actor_id: str = ""
    actor_name: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    previous_hash: Optional[str] = None
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.record_id:
            self.record_id = f"aud-{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "record_id": self.record_id,
            "request_id": self.request_id,
            "event_type": self.event_type.value,
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "details": self.details,
            "content_hash": self.content_hash,
            "previous_hash": self.previous_hash,
            "timestamp": self.timestamp,
        }


@dataclass
class MerkleProof:
    """A Merkle proof for verifying a specific record's inclusion.

    Contains the root hash, sibling hashes, and direction indicators
    needed to recompute the Merkle root and verify inclusion.
    """

    record_id: str = ""
    root_hash: str = ""
    sibling_hashes: List[str] = field(default_factory=list)
    direction: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "record_id": self.record_id,
            "root_hash": self.root_hash,
            "sibling_hashes": self.sibling_hashes,
            "direction": self.direction,
        }


class ApprovalAuditMerkle:
    """Merkle-chain audit trail for all HITL events.

    Every event is recorded with a SHA-256 content hash that chains
    to the previous record, creating a tamper-evident log.
    """

    def __init__(self, db_path: str = "audit_merkle.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    # ── DB Initialisation ──────────────────────────────────

    def _init_db(self) -> None:
        """Create the audit records table if it does not exist."""
        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_records (
                    record_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor_id TEXT NOT NULL DEFAULT '',
                    actor_name TEXT NOT NULL DEFAULT '',
                    details TEXT NOT NULL DEFAULT '{}',
                    content_hash TEXT NOT NULL,
                    previous_hash TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_request
                ON audit_records(request_id, timestamp ASC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_hash
                ON audit_records(content_hash)
            """)
            conn.commit()
            conn.close()

        self._with_retry(_do_init)

    # ── Core Operations ────────────────────────────────────

    def record_event(
        self,
        request_id: str,
        event_type: str,
        actor_id: str,
        actor_name: str,
        details: Dict[str, Any],
    ) -> AuditRecord:
        """Record an event in the audit Merkle chain.

        Computes SHA-256 content hash, chains to the previous record.
        """
        if not request_id:
            raise ValueError("request_id is required")

        # Normalize event_type to AuditEventType
        if isinstance(event_type, str):
            try:
                event_type_enum = AuditEventType(event_type)
            except ValueError:
                event_type_enum = AuditEventType.APPROVAL_REQUESTED
        else:
            event_type_enum = event_type

        # Get previous hash
        previous_hash = self._get_last_hash()

        record = AuditRecord(
            request_id=request_id,
            event_type=event_type_enum,
            actor_id=actor_id,
            actor_name=actor_name,
            details=details,
            previous_hash=previous_hash,
        )

        # Compute content hash: SHA-256(record data + previous_hash)
        record.content_hash = self._compute_content_hash(record, previous_hash)

        with self._lock:
            self._persist_record(record, insert=True)

        logger.info(
            "ApprovalAuditMerkle: Recorded %s for request %s (hash=%s…)",
            event_type_enum.value, request_id, record.content_hash[:16],
        )
        return record

    def get_audit_trail(self, request_id: str) -> List[AuditRecord]:
        """Get all audit records for a request, in chronological order."""
        def _do_query() -> List[AuditRecord]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM audit_records
                   WHERE request_id = ?
                   ORDER BY timestamp ASC""",
                (request_id,),
            ).fetchall()
            conn.close()
            return [self._row_to_record(r) for r in rows]

        return self._with_retry(_do_query, fallback=[])

    def verify_chain_integrity(
        self, request_id: str,
    ) -> Tuple[bool, Optional[int]]:
        """Verify all hashes and chain links for a request's audit trail.

        Returns (is_valid, failed_at_index) where failed_at_index is the
        index of the first broken link, or None if the chain is intact.
        """
        records = self.get_audit_trail(request_id)
        if not records:
            return (True, None)

        for i, record in enumerate(records):
            # Verify content hash
            previous_hash = record.previous_hash or GENESIS_HASH
            expected_hash = self._compute_content_hash(record, previous_hash)
            if record.content_hash != expected_hash:
                logger.warning(
                    "ApprovalAuditMerkle: Content hash mismatch at index %d "
                    "for request %s", i, request_id,
                )
                return (False, i)

            # Verify chain link — per-request, the first record may link to
            # a global record from another request, which is valid.
            # Only verify internal links (i > 0) within the same request.
            if i > 0:
                if record.previous_hash != records[i - 1].content_hash:
                    logger.warning(
                        "ApprovalAuditMerkle: Chain link broken at index %d "
                        "for request %s", i, request_id,
                    )
                    return (False, i)

        return (True, None)

    def verify_global_integrity(self) -> Tuple[bool, Optional[int]]:
        """Verify the entire global audit chain.

        Returns (is_valid, failed_at_index) across ALL records globally.
        """
        def _do_query() -> List[AuditRecord]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM audit_records
                   ORDER BY timestamp ASC""",
            ).fetchall()
            conn.close()
            return [self._row_to_record(r) for r in rows]

        records = self._with_retry(_do_query, fallback=[])
        if not records:
            return (True, None)

        for i, record in enumerate(records):
            previous_hash = record.previous_hash or GENESIS_HASH
            expected_hash = self._compute_content_hash(record, previous_hash)
            if record.content_hash != expected_hash:
                return (False, i)

            if i == 0:
                if record.previous_hash is not None and record.previous_hash != GENESIS_HASH:
                    return (False, i)
            else:
                if record.previous_hash != records[i - 1].content_hash:
                    return (False, i)

        return (True, None)

    def get_merkle_proof(self, record_id: str) -> MerkleProof:
        """Generate a Merkle proof for a specific record.

        Constructs a proof path from the record to the current Merkle root.
        """
        # Get all records sorted by timestamp
        def _do_query() -> List[AuditRecord]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM audit_records
                   ORDER BY timestamp ASC""",
            ).fetchall()
            conn.close()
            return [self._row_to_record(r) for r in rows]

        all_records = self._with_retry(_do_query, fallback=[])
        if not all_records:
            return MerkleProof(record_id=record_id)

        # Find the target record index
        target_idx = -1
        for idx, rec in enumerate(all_records):
            if rec.record_id == record_id:
                target_idx = idx
                break

        if target_idx == -1:
            return MerkleProof(record_id=record_id)

        # Build Merkle tree from all content hashes and compute proof
        hashes = [r.content_hash for r in all_records]
        sibling_hashes: List[str] = []
        direction: List[str] = []

        # Simple binary Merkle proof
        idx = target_idx
        while len(hashes) > 1:
            if idx % 2 == 0:
                # Left node — sibling is right
                sibling_idx = idx + 1
                direction.append("right")
            else:
                # Right node — sibling is left
                sibling_idx = idx - 1
                direction.append("left")

            if sibling_idx < len(hashes):
                sibling_hashes.append(hashes[sibling_idx])
            else:
                # Pad with the current hash if odd number
                sibling_hashes.append(hashes[idx])
                direction[-1] = "left"  # treat as self

            # Combine pairs
            new_hashes: List[str] = []
            for j in range(0, len(hashes), 2):
                left = hashes[j]
                right = hashes[j + 1] if j + 1 < len(hashes) else left
                combined = hashlib.sha256(
                    f"{left}{right}".encode()
                ).hexdigest()
                new_hashes.append(combined)

            hashes = new_hashes
            idx = idx // 2

        return MerkleProof(
            record_id=record_id,
            root_hash=hashes[0] if hashes else "",
            sibling_hashes=sibling_hashes,
            direction=direction,
        )

    def export_audit_trail(self, request_id: str) -> Dict[str, Any]:
        """Export complete audit trail with integrity verification result."""
        records = self.get_audit_trail(request_id)
        is_valid, failed_at = self.verify_chain_integrity(request_id)

        return {
            "request_id": request_id,
            "records": [r.to_dict() for r in records],
            "total_records": len(records),
            "integrity_valid": is_valid,
            "integrity_failed_at": failed_at,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

    def compute_root_hash(self) -> str:
        """Compute the current Merkle root from all records.

        Builds a binary Merkle tree from all content hashes and
        returns the root hash.
        """
        def _do_query() -> List[str]:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT content_hash FROM audit_records ORDER BY timestamp ASC",
            ).fetchall()
            conn.close()
            return [r[0] for r in rows]

        hashes = self._with_retry(_do_query, fallback=[])
        if not hashes:
            return GENESIS_HASH

        # Build Merkle tree
        while len(hashes) > 1:
            new_hashes: List[str] = []
            for i in range(0, len(hashes), 2):
                left = hashes[i]
                right = hashes[i + 1] if i + 1 < len(hashes) else left
                combined = hashlib.sha256(
                    f"{left}{right}".encode()
                ).hexdigest()
                new_hashes.append(combined)
            hashes = new_hashes

        return hashes[0]

    # ── Private Helpers ────────────────────────────────────

    def _get_last_hash(self) -> str:
        """Get the content_hash of the most recent record (for chaining)."""
        def _do_query() -> str:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                """SELECT content_hash FROM audit_records
                   ORDER BY timestamp DESC LIMIT 1""",
            ).fetchone()
            conn.close()
            if row:
                return row[0]
            return GENESIS_HASH

        return self._with_retry(_do_query, fallback=GENESIS_HASH)

    @staticmethod
    def _compute_content_hash(record: AuditRecord, previous_hash: str) -> str:
        """Compute the SHA-256 content hash for a record."""
        payload = json.dumps({
            "request_id": record.request_id,
            "event_type": record.event_type.value if isinstance(record.event_type, AuditEventType) else record.event_type,
            "actor_id": record.actor_id,
            "actor_name": record.actor_name,
            "details": record.details,
            "previous_hash": previous_hash,
            "timestamp": record.timestamp,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def _persist_record(self, record: AuditRecord, *, insert: bool) -> None:
        """Insert or update an audit record in the database."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            if insert:
                conn.execute(
                    """INSERT INTO audit_records
                       (record_id, request_id, event_type, actor_id,
                        actor_name, details, content_hash, previous_hash,
                        timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.record_id,
                        record.request_id,
                        record.event_type.value,
                        record.actor_id,
                        record.actor_name,
                        json.dumps(record.details),
                        record.content_hash,
                        record.previous_hash,
                        record.timestamp,
                    ),
                )
            else:
                conn.execute(
                    """UPDATE audit_records SET
                       details=?, content_hash=?, previous_hash=?
                       WHERE record_id=?""",
                    (
                        json.dumps(record.details),
                        record.content_hash,
                        record.previous_hash,
                        record.record_id,
                    ),
                )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> AuditRecord:
        """Convert a database row to an AuditRecord."""
        return AuditRecord(
            record_id=row["record_id"],
            request_id=row["request_id"],
            event_type=AuditEventType(row["event_type"]),
            actor_id=row["actor_id"] or "",
            actor_name=row["actor_name"] or "",
            details=json.loads(row["details"] or "{}"),
            content_hash=row["content_hash"],
            previous_hash=row["previous_hash"],
            timestamp=row["timestamp"],
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
                    "ApprovalAuditMerkle: DB retry %d/%d — %s",
                    attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    time.sleep(_RETRY_DELAY * attempt)
            except Exception as exc:
                last_exc = exc
                logger.error("ApprovalAuditMerkle: DB error — %s", exc)
                break
        logger.error("ApprovalAuditMerkle: All retries exhausted — %s", last_exc)
        return fallback


# ── Singleton ─────────────────────────────────────────────

_audit_merkle_instance: Optional[ApprovalAuditMerkle] = None
_audit_merkle_lock = threading.Lock()


def get_approval_audit_merkle(
    db_path: str = "audit_merkle.sqlite",
) -> ApprovalAuditMerkle:
    """Get or create the global ApprovalAuditMerkle instance."""
    global _audit_merkle_instance
    with _audit_merkle_lock:
        if _audit_merkle_instance is None:
            _audit_merkle_instance = ApprovalAuditMerkle(db_path=db_path)
        return _audit_merkle_instance


def reset_approval_audit_merkle() -> None:
    """Reset the global ApprovalAuditMerkle (for testing)."""
    global _audit_merkle_instance
    _audit_merkle_instance = None


__all__ = [
    "AuditEventType",
    "AuditRecord",
    "MerkleProof",
    "GENESIS_HASH",
    "ApprovalAuditMerkle",
    "get_approval_audit_merkle",
    "reset_approval_audit_merkle",
]
