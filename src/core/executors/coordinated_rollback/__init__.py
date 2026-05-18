"""
ZENIC-AGENTS - Coordinated Rollback Manager (A3 Rollback Enhancement)

Multi-resource coordinated rollback using SAGA-style compensation.
"""

from src.core.executors.coordinated_rollback._types import (
    ResourceType,
    ActionStatus,
    ResourceRecord,
    CoordinatedAction,
    CoordinatedRollbackResult,
)
from src.core.executors.coordinated_rollback._manager import (
    CoordinatedRollbackManager,
    get_coordinated_rollback_manager,
    reset_coordinated_rollback_manager,
)

__all__ = [
    "ResourceType",
    "ActionStatus",
    "ResourceRecord",
    "CoordinatedAction",
    "CoordinatedRollbackResult",
    "CoordinatedRollbackManager",
    "get_coordinated_rollback_manager",
    "reset_coordinated_rollback_manager",
]
