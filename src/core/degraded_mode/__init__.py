"""
Zenic-Agents Asistente - Degraded Mode Package (Phase 6.4)

System operating modes based on license and security state.

Modes:
- NORMAL: Full functionality
- DEGRADED: Limited features (no executors, read-only dashboards)
- PARALYSIS L1: Read-only mode (only viewing, no modifications)
- PARALYSIS L2: Emergency lockdown (admin-only access)
"""

from .types import (
    DegradationLevel,
    DegradationReason,
    DegradationState,
)

from .persistence import DegradationPersistence

from .manager import (
    DegradedModeManager,
    SystemMode,
    ModeTransition,
    get_degraded_mode_manager,
    reset_degraded_mode_manager,
)

from .mode_parts.capabilities import (
    ModeCapabilities,
    MODE_CAPABILITIES,
)

__all__ = [
    # Types
    "DegradationLevel",
    "DegradationReason",
    "DegradationState",
    # Persistence
    "DegradationPersistence",
    # Manager
    "DegradedModeManager",
    "SystemMode",
    "ModeCapabilities",
    "ModeTransition",
    "MODE_CAPABILITIES",
    # Singleton helpers
    "get_degraded_mode_manager",
    "reset_degraded_mode_manager",
]
