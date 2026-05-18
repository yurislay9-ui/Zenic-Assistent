"""
Zenic-Agents Asistente - Audit Trail in Merkle Ledger (Phase 5)

Cryptographic audit trail for all Human-in-the-Loop events. Every
HITL event is recorded in a hash-chained Merkle structure that provides
tamper-evident integrity verification.
"""

from ._types import (
    AuditEventType,
    AuditRecord,
    MerkleProof,
    GENESIS_HASH,
    _MAX_RETRIES,
    _RETRY_DELAY,
)
from ._mixin_core import ApprovalAuditMerkle

# ── Singleton ─────────────────────────────────────────────

import threading
from typing import Optional

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
