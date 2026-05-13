"""
Audit Logging — Types and Data Model.

Contains AuditEventType enum, AuditSeverity enum,
and the AuditEvent dataclass.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

try:
    from ..tracing import get_current_trace_id, get_current_span_id
except ImportError:
    def get_current_trace_id() -> str:
        return ""
    def get_current_span_id() -> str:
        return ""


class AuditEventType(str, Enum):
    """Categories of auditable events."""
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAILURE = "auth.login.failure"
    AUTH_LOGOUT = "auth.logout"
    AUTH_TOKEN_REFRESH = "auth.token.refresh"
    AUTH_TOKEN_REVOKED = "auth.token.revoked"
    AUTH_API_KEY_CREATED = "auth.api_key.created"
    AUTH_API_KEY_REVOKED = "auth.api_key.revoked"
    TENANT_CREATED = "tenant.created"
    TENANT_UPDATED = "tenant.updated"
    TENANT_DEPROVISIONED = "tenant.deprovisioned"
    TENANT_USER_ASSIGNED = "tenant.user_assigned"
    DATA_ACCESS = "data.access"
    DATA_MODIFICATION = "data.modification"
    DATA_EXPORT = "data.export"
    DATA_DELETE = "data.delete"
    SECURITY_VIOLATION = "security.violation"
    RATE_LIMIT_EXCEEDED = "security.rate_limit_exceeded"
    CIRCUIT_BREAKER_OPEN = "security.circuit_breaker_open"
    INPUT_REJECTED = "security.input_rejected"
    CORS_REJECTED = "security.cors_rejected"
    SAGA_STARTED = "saga.started"
    SAGA_COMPLETED = "saga.completed"
    SAGA_COMPENSATED = "saga.compensated"
    SAGA_FAILED = "saga.failed"
    ADMIN_ROLE_CHANGE = "admin.role_change"
    ADMIN_CONFIG_CHANGE = "admin.config_change"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """A single auditable event."""
    event_id: str = ""
    event_type: AuditEventType = AuditEventType.DATA_ACCESS
    severity: AuditSeverity = AuditSeverity.INFO
    timestamp: str = ""
    trace_id: str = ""
    span_id: str = ""
    tenant_id: str = "__anonymous__"
    user_id: Optional[int] = None
    ip_address: str = ""
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id:
            self.event_id = f"aud-{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.trace_id:
            self.trace_id = get_current_trace_id()
        if not self.span_id:
            self.span_id = get_current_span_id()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "ip_address": self.ip_address,
            "description": self.description,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)
