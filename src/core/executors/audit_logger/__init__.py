"""
ZENIC-AGENTS - Executor Audit Logger (Phase 3)

Structured audit logging for all executor actions.
Dual output: structured log (JSON) + SQLite for query/retention.
Integrates with the Merkle Ledger for tamper-proof audit trails.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from ._types import AuditEntry, AuditQuery
from ._merkle import AuditMerkleChain
from ._persistence import AuditPersistence

logger = logging.getLogger(__name__)

__all__ = [
    "AuditEntry",
    "AuditQuery",
    "AuditMerkleChain",
    "AuditPersistence",
    "ExecutorAuditLogger",
    "get_default_audit_logger",
    "reset_audit_logger",
]


class ExecutorAuditLogger:
    """Main audit logger for the executor system.

    Combines:
      - Structured JSON logging (for log aggregation)
      - SQLite persistence (for querying and retention)
      - Merkle chain (for tamper-proof integrity)

    Usage:
        audit = ExecutorAuditLogger()
        entry = audit.log_action(
            action_type="database",
            operation="delete",
            executor_class="DatabaseExecutor",
            verdict="CONFIRM",
            success=True,
            duration_ms=45.2,
        )
    """

    def __init__(
        self,
        db_path: str = "executor_audit.db",
        enable_merkle: bool = True,
        enable_persistence: bool = True,
    ) -> None:
        self._merkle = AuditMerkleChain() if enable_merkle else None
        self._persistence = AuditPersistence(db_path) if enable_persistence else None
        self._buffer: List[AuditEntry] = []
        self._buffer_size = 50
        self._total_logged = 0

    def log_action(
        self,
        action_type: str,
        operation: str,
        executor_class: str,
        verdict: str,
        success: bool,
        duration_ms: float = 0.0,
        user_id: str = "",
        tenant_id: str = "",
        session_id: str = "",
        request_id: str = "",
        risk_score: float = 0.0,
        category: str = "",
        error: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """Log an executor action with full audit trail."""
        entry = AuditEntry(
            action_type=action_type,
            operation=operation,
            executor_class=executor_class,
            verdict=verdict,
            success=success,
            duration_ms=duration_ms,
            user_id=user_id,
            tenant_id=tenant_id,
            session_id=session_id,
            request_id=request_id,
            risk_score=risk_score,
            category=category,
            error=error,
            metadata=metadata or {},
        )

        # Seal with Merkle chain
        if self._merkle:
            self._merkle.seal(entry)

        # Structured log output
        logger.info(
            "ExecutorAudit: action=%s op=%s executor=%s verdict=%s "
            "success=%s risk=%.2f duration=%.1fms merkle=%s",
            entry.action_type, entry.operation, entry.executor_class,
            entry.verdict, entry.success, entry.risk_score,
            entry.duration_ms, entry.merkle_hash[:16],
        )

        # Buffer and flush
        self._buffer.append(entry)
        self._total_logged += 1
        if len(self._buffer) >= self._buffer_size:
            self.flush()

        return entry

    def flush(self) -> None:
        """Flush buffered entries to persistence."""
        if not self._persistence or not self._buffer:
            return
        for entry in self._buffer:
            try:
                self._persistence.save(entry)
            except Exception as e:
                logger.error("ExecutorAuditLogger: Failed to persist entry %s: %s", entry.entry_id, e)
        self._buffer.clear()

    def query(self, q: AuditQuery) -> List[AuditEntry]:
        """Query audit entries."""
        if self._persistence:
            return self._persistence.query(q)
        return []

    def verify_integrity(self) -> bool:
        """Verify the integrity of the audit trail."""
        if not self._merkle or not self._persistence:
            return True
        entries = self._persistence.query(AuditQuery(limit=10000))
        return self._merkle.verify(entries)

    def prune(self, days: int = 90) -> int:
        """Prune entries older than N days."""
        if not self._persistence:
            return 0
        cutoff = time.time() - (days * 86400)
        return self._persistence.prune(cutoff)

    @property
    def stats(self) -> Dict[str, Any]:
        """Get audit logger statistics."""
        return {
            "total_logged": self._total_logged,
            "buffer_size": len(self._buffer),
            "merkle_enabled": self._merkle is not None,
            "persistence_enabled": self._persistence is not None,
            "last_merkle_hash": self._merkle.last_hash[:16] if self._merkle else "",
        }


# ──────────────────────────────────────────────────────────────
#  GLOBAL INSTANCE
# ──────────────────────────────────────────────────────────────

_default_audit_logger: Optional[ExecutorAuditLogger] = None


def get_default_audit_logger() -> ExecutorAuditLogger:
    """Get or create the global audit logger instance."""
    global _default_audit_logger
    if _default_audit_logger is None:
        _default_audit_logger = ExecutorAuditLogger()
    return _default_audit_logger


def reset_audit_logger() -> None:
    """Reset the global audit logger (for testing)."""
    global _default_audit_logger
    _default_audit_logger = None
