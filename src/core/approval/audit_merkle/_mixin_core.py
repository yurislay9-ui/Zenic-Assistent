"""
Audit Merkle — Core Mixin.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ._types import AuditRecord, AuditEventType, MerkleProof, GENESIS_HASH
from ._mixin_persistence import AuditMerklePersistenceMixin

logger = logging.getLogger(__name__)


class ApprovalAuditMerkle(AuditMerklePersistenceMixin):
    """Merkle-chain audit trail for all HITL events.

    Every event is recorded with a SHA-256 content hash that chains
    to the previous record, creating a tamper-evident log.
    """

    def __init__(self, db_path: str = "audit_merkle.sqlite") -> None:
        self._db_path = db_path
        import threading
        self._lock = threading.RLock()
        self._init_db()

    # ── Core Operations ────────────────────────────────────

    def record_event(
        self,
        request_id: str,
        event_type: str,
        actor_id: str,
        actor_name: str,
        details: Dict[str, Any],
    ) -> AuditRecord:
        """Record an event in the audit Merkle chain."""
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

        previous_hash = self._get_last_hash()

        record = AuditRecord(
            request_id=request_id,
            event_type=event_type_enum,
            actor_id=actor_id,
            actor_name=actor_name,
            details=details,
            previous_hash=previous_hash,
        )

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
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
        """Verify all hashes and chain links for a request's audit trail."""
        records = self.get_audit_trail(request_id)
        if not records:
            return (True, None)

        for i, record in enumerate(records):
            previous_hash = record.previous_hash or GENESIS_HASH
            expected_hash = self._compute_content_hash(record, previous_hash)
            if record.content_hash != expected_hash:
                logger.warning(
                    "ApprovalAuditMerkle: Content hash mismatch at index %d "
                    "for request %s", i, request_id,
                )
                return (False, i)

            if i > 0:
                if record.previous_hash != records[i - 1].content_hash:
                    logger.warning(
                        "ApprovalAuditMerkle: Chain link broken at index %d "
                        "for request %s", i, request_id,
                    )
                    return (False, i)

        return (True, None)

    def verify_global_integrity(self) -> Tuple[bool, Optional[int]]:
        """Verify the entire global audit chain."""
        def _do_query() -> List[AuditRecord]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
        """Generate a Merkle proof for a specific record."""
        def _do_query() -> List[AuditRecord]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """SELECT * FROM audit_records
                   ORDER BY timestamp ASC""",
            ).fetchall()
            conn.close()
            return [self._row_to_record(r) for r in rows]

        all_records = self._with_retry(_do_query, fallback=[])
        if not all_records:
            return MerkleProof(record_id=record_id)

        target_idx = -1
        for idx, rec in enumerate(all_records):
            if rec.record_id == record_id:
                target_idx = idx
                break

        if target_idx == -1:
            return MerkleProof(record_id=record_id)

        hashes = [r.content_hash for r in all_records]
        sibling_hashes: List[str] = []
        direction: List[str] = []

        idx = target_idx
        while len(hashes) > 1:
            if idx % 2 == 0:
                sibling_idx = idx + 1
                direction.append("right")
            else:
                sibling_idx = idx - 1
                direction.append("left")

            if sibling_idx < len(hashes):
                sibling_hashes.append(hashes[sibling_idx])
            else:
                sibling_hashes.append(hashes[idx])
                direction[-1] = "left"

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
        """Compute the current Merkle root from all records."""
        def _do_query() -> List[str]:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT content_hash FROM audit_records ORDER BY timestamp ASC",
            ).fetchall()
            conn.close()
            return [r[0] for r in rows]

        hashes = self._with_retry(_do_query, fallback=[])
        if not hashes:
            return GENESIS_HASH

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
