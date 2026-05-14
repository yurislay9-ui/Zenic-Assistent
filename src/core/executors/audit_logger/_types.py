"""
ZENIC-AGENTS - Executor Audit Logger: Types

AuditEntry, AuditQuery dataclasses for structured audit logging.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class AuditEntry:
    """A single audit log entry for an executor action."""
    entry_id: str = ""
    action_type: str = ""
    operation: str = ""
    executor_class: str = ""
    verdict: str = ""              # ALLOW, CONFIRM, DENY, RATE_LIMITED
    success: bool = False
    duration_ms: float = 0.0
    user_id: str = ""
    tenant_id: str = ""
    session_id: str = ""
    request_id: str = ""
    risk_score: float = 0.0
    category: str = ""             # safe, moderate, destructive, financial, system
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    merkle_hash: str = ""
    prev_hash: str = ""
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if not self.entry_id:
            self.entry_id = uuid.uuid4().hex[:16]
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass
class AuditQuery:
    """Query parameters for searching audit entries."""
    action_type: Optional[str] = None
    executor_class: Optional[str] = None
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    success: Optional[bool] = None
    verdict: Optional[str] = None
    category: Optional[str] = None
    from_timestamp: Optional[float] = None
    to_timestamp: Optional[float] = None
    limit: int = 100
    offset: int = 0
