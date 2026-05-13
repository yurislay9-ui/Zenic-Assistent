"""
ZENIC-AGENTS - Safety Gate for Executors (Phase 3)

Pre-execution validation layer that enforces deterministic safety rules
BEFORE any executor runs. Safety Gate veto is ABSOLUTE — no override possible.
"""

from ._types import SafetyVerdict, ActionCategory, SafetyRule, SafetyCheckResult, SAFETY_RULES
from ._gate import ActionRateLimiter, SafetyGate, get_default_safety_gate, reset_safety_gate

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
]
