"""
Zenic-Agents Asistente - Rollback/Auto-Revert Post-Approval (Phase 5)

SAGA-inspired compensation pattern for reverting approved actions.
When an approved action needs to be undone, all registered compensation
actions are executed in reverse order.

Triggers:
  - APPROVAL_EXPIRED: The approval expired and needs auto-revert
  - ACTION_FAILED: The approved action failed during execution
  - MANUAL_UNDO: A user explicitly requested an undo
  - COMPLIANCE_VIOLATION: A compliance check post-approval failed

Integration:
  - Called by ExpiryManager.execute_revert() and by the undo API.
  - Each rollback is hashed into the Merkle ledger for immutability.

Persistence: SQLite with retry logic.
"""

from ._snapshots import (
    CompensationAction,
    RollbackRecord,
    RollbackStatus,
    RollbackTrigger,
)
from ._manager import (
    RollbackManager,
    get_rollback_manager,
    reset_rollback_manager,
)

__all__ = [
    "RollbackStatus",
    "RollbackTrigger",
    "CompensationAction",
    "RollbackRecord",
    "RollbackManager",
    "get_rollback_manager",
    "reset_rollback_manager",
]
