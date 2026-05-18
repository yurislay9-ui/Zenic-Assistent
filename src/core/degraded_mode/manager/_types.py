"""Types and constants for manager."""

from __future__ import annotations
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from .persistence import DegradationPersistence
from .types import DegradationLevel, DegradationReason, DegradationState

# Modes: NORMAL(0) -> DEGRADED(1) -> PARALYSIS_1(2) -> PARALYSIS_2(3)

logger = logging.getLogger(__name__)

class SystemMode(str, Enum):
    """System operating modes, from most to least permissive."""
    NORMAL = "normal"
    RESTRICTIVE = "restrictive"
    DEGRADED = "degraded"
    PARALYSIS_L1 = "paralysis_l1"
    PARALYSIS_L2 = "paralysis_l2"
    PARALYSIS_L3 = "paralysis_l3"

    @property
    def is_read_only(self) -> bool:
        return self in (SystemMode.DEGRADED, SystemMode.PARALYSIS_L1,
                        SystemMode.PARALYSIS_L2, SystemMode.PARALYSIS_L3)

    @property
    def allows_write(self) -> bool:
        return self in (SystemMode.NORMAL, SystemMode.RESTRICTIVE)

    @property
    def allows_delete(self) -> bool:
        return self == SystemMode.NORMAL

    @property
    def allows_export(self) -> bool:
        return True

    @property
    def paralysis_level(self) -> int:
        return {
            SystemMode.PARALYSIS_L1: 1,
            SystemMode.PARALYSIS_L2: 2,
            SystemMode.PARALYSIS_L3: 3,
        }.get(self, 0)

    @property
    def degradation_level(self) -> DegradationLevel:
        _m = {SystemMode.NORMAL: DegradationLevel.NORMAL,
              SystemMode.RESTRICTIVE: DegradationLevel.DEGRADED,
              SystemMode.DEGRADED: DegradationLevel.DEGRADED,
              SystemMode.PARALYSIS_L1: DegradationLevel.PARALYSIS_1,
              SystemMode.PARALYSIS_L2: DegradationLevel.PARALYSIS_2,
              SystemMode.PARALYSIS_L3: DegradationLevel.PARALYSIS_2}
        return _m.get(self, DegradationLevel.NORMAL)



@dataclass
class ModeTransition:
    """Record of a mode transition event."""
    from_mode: SystemMode
    to_mode: SystemMode
    reason: str
    timestamp: float = 0.0
    operator: str = "system"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = time.time()


_FEATURE_RESTRICTIONS: Dict[DegradationLevel, List[str]] = {
    DegradationLevel.NORMAL: [],
    DegradationLevel.DEGRADED: ["create", "update", "delete"],
    DegradationLevel.PARALYSIS_1: ["create", "update", "delete", "export_bulk"],
    DegradationLevel.PARALYSIS_2: ["create", "update", "delete", "export_bulk", "read_sensitive"],
}

_degraded_mode_manager: Optional[Any] = None
