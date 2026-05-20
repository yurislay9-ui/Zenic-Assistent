"""
Dispatch Action — Types.

Contains DispatchRequest and DispatchResult dataclasses.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..safety_gate import SafetyVerdict, SafetyCheckResult
from ..audit_logger import AuditEntry
from ..base import ActionResult


@dataclass
class DispatchRequest:
    """A request to dispatch an action through the pipeline."""
    action_type: str
    config: Dict[str, Any]
    context: Dict[str, Any] = field(default_factory=dict)
    action_id: str = ""
    user_id: str = ""
    tenant_id: str = ""
    session_id: str = ""
    request_id: str = ""
    blueprint_name: str = ""
    # SECURITY: skip_safety_gate REMOVED — safety gate is ALWAYS enforced.
    # Any code that previously set skip_safety_gate=True must be updated.
    skip_audit: bool = False
    dry_run: bool = False

    def __post_init__(self) -> None:
        if not self.action_id:
            self.action_id = uuid.uuid4().hex[:12]


@dataclass
class DispatchResult:
    """Result of a dispatch through the full pipeline."""
    action_id: str
    success: bool
    safety_verdict: SafetyVerdict
    executor_result: Optional[ActionResult] = None
    audit_entry: Optional[AuditEntry] = None
    safety_result: Optional[SafetyCheckResult] = None
    blueprint_errors: List[str] = field(default_factory=list)
    total_duration_ms: float = 0.0
    pipeline_stages: Dict[str, float] = field(default_factory=dict)
