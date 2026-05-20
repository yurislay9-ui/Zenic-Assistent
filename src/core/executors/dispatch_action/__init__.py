"""
ZENIC-AGENTS - Dispatch Action (Phase 3 + Phase 5 + Phase C1)

DAG → Executor pipeline integration.
Bridges the DAG pipeline with the executor system:

  DAG Node "DISPATCH_ACTION" → Safety Gate → Executor → Audit Logger → Merkle Ledger

Phase 5: Supports dynamic Blueprint switching from the
Blueprint Registry when blueprint_name is provided.

Phase C1: Supports dry_run mode — simulate execution without real effects.
"""

from ._types import DispatchRequest, DispatchResult
from ._mixin_core import ActionDispatcher
from ._dag import exec_dispatch_action, get_default_dispatcher, reset_dispatcher

__all__ = [
    "DispatchRequest",
    "DispatchResult",
    "ActionDispatcher",
    "exec_dispatch_action",
    "get_default_dispatcher",
    "reset_dispatcher",
]
