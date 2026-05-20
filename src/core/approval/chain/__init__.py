"""
Zenic-Agents Asistente - Approval Chain System (Phase 6.1b)

Chain-of-approval system for critical actions. When SafetyGate returns
APPROVE, the action enters the approval chain. Approvers with sufficient
role must explicitly approve before execution proceeds.

Flow:
  Action → SafetyGate(APPROVE) → ApprovalChain.create_request()
  → Approvers notified → approve()/reject() → Action dispatched

Persistence: SQLite via chain_parts/persistence.py.
Timeout: Auto-escalation to higher authority after configurable delay.
"""

from ._validation import (
    ApprovalPriority,
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
    MemoryApprovalPayload,
)
from ._chain import (
    ApprovalChain,
    get_approval_chain,
    reset_approval_chain,
)

__all__ = [
    "ApprovalStatus",
    "ApprovalPriority",
    "ApprovalRequest",
    "ApprovalResult",
    "MemoryApprovalPayload",
    "ApprovalChain",
    "get_approval_chain",
    "reset_approval_chain",
]
