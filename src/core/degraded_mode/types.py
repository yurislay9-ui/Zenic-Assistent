"""
Zenic-Agents Asistente - Degraded Mode Type Definitions (Phase 6.4)

Core types for the degraded mode / paralysis system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class DegradationLevel(int, Enum):
    """Numeric degradation levels, from fully operational to emergency lockdown.

    Values are ordered so that higher integers imply stricter restrictions.
    """
    NORMAL = 0        # Full functionality
    DEGRADED = 1      # Limited features (no executors, read-only dashboards)
    PARALYSIS_1 = 2   # Read-only mode (only viewing, no modifications)
    PARALYSIS_2 = 3   # Emergency lockdown (admin-only access)

    @property
    def is_read_only(self) -> bool:
        return self.value >= DegradationLevel.PARALYSIS_1.value

    @property
    def allows_write(self) -> bool:
        return self.value <= DegradationLevel.DEGRADED.value

    @property
    def allows_delete(self) -> bool:
        return self.value == DegradationLevel.NORMAL.value


class DegradationReason(str, Enum):
    """Why the system entered a degraded state."""
    NONE = "none"
    TRIAL_EXPIRED = "trial_expired"
    TAMPERING_DETECTED = "tampering_detected"
    LICENSE_INVALID = "license_invalid"
    PAYMENT_FAILED = "payment_failed"
    MANUAL = "manual"
    INTEGRITY_VIOLATION = "integrity_violation"


@dataclass
class DegradationState:
    """Snapshot of the current degradation status."""
    level: DegradationLevel = DegradationLevel.NORMAL
    reason: DegradationReason = DegradationReason.NONE
    message: str = ""
    entered_at: float = 0.0
    restricted_features: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_normal(self) -> bool:
        return self.level == DegradationLevel.NORMAL

    @property
    def is_paralysis(self) -> bool:
        return self.level.value >= DegradationLevel.PARALYSIS_1.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "level_name": self.level.name,
            "reason": self.reason.value,
            "message": self.message,
            "entered_at": self.entered_at,
            "restricted_features": self.restricted_features,
            "metadata": self.metadata,
        }
