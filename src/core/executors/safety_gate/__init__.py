"""
ZENIC-AGENTS - Safety Gate for Executors (Phase 3 + Phase D)

Pre-execution validation layer that enforces deterministic safety rules
BEFORE any executor runs. Safety Gate veto is ABSOLUTE — no override possible.

Phase D extensions:
    - DomainSafetyGate: domain-specific rules + compliance validation
    - ComplianceResult: compliance check result
    - DomainSafetyCheckResult: extended safety check result with domain info
"""

from ._types import SafetyVerdict, ActionCategory, SafetyRule, SafetyCheckResult, SAFETY_RULES
from ._gate import ActionRateLimiter, SafetyGate, get_default_safety_gate, reset_safety_gate
from .domain_gate import (
    DomainSafetyGate,
    ComplianceResult,
    DomainSafetyCheckResult,
    get_default_domain_safety_gate,
)

__all__ = [
    "SafetyVerdict",
    "ActionCategory",
    "SafetyRule",
    "SafetyCheckResult",
    "SAFETY_RULES",
    "ActionRateLimiter",
    "SafetyGate",
    "get_default_safety_gate",
    "reset_safety_gate",
    "DomainSafetyGate",
    "ComplianceResult",
    "DomainSafetyCheckResult",
    "get_default_domain_safety_gate",
]
