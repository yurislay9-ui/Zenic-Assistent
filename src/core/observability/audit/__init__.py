"""
ZENIC-AGENTS v16 - Audit Logging (Phase 5)

Comprehensive audit trail for security and compliance.
Records all security-relevant events with trace correlation
for end-to-end observability.
"""

import threading
from typing import Optional

from ._types import AuditEventType, AuditSeverity, AuditEvent
from ._logger import AuditLogger

__all__ = [
    "AuditLogger",
    "AuditEvent",
    "AuditEventType",
    "AuditSeverity",
    "get_audit_logger",
]


# ── Singleton ─────────────────────────────────────────────
_audit_logger_instance: Optional[AuditLogger] = None
_audit_logger_lock = threading.Lock()


def get_audit_logger(
    db_path: str = "audit_log.sqlite",
    retention_days: int = 90,
) -> AuditLogger:
    """Get or create the singleton AuditLogger."""
    global _audit_logger_instance
    with _audit_logger_lock:
        if _audit_logger_instance is None:
            _audit_logger_instance = AuditLogger(
                db_path=db_path,
                retention_days=retention_days,
            )
        return _audit_logger_instance
