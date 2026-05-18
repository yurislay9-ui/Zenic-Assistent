"""
ZENIC-AGENTS - Objective Data Model & Persistence (Phase D1)

Objective data model and SQLite persistence for the Autopilot by Objectives
system. Objectives represent business goals like "reduce overdue invoices to <5%"
with measurable targets, priorities, and lifecycle management.

Thread-safe: All public methods guarded by RLock.
Retry logic: DB operations wrapped with 3 retries, base 0.5s backoff.
"""

from ._scoring import (
    ObjectiveStatus,
    ObjectivePriority,
    ObjectiveTarget,
    Objective,
)
from ._manager import (
    ObjectiveStore,
    get_objective_store,
    reset_objective_store,
)

__all__ = [
    "ObjectiveStatus",
    "ObjectivePriority",
    "ObjectiveTarget",
    "Objective",
    "ObjectiveStore",
    "get_objective_store",
    "reset_objective_store",
]
