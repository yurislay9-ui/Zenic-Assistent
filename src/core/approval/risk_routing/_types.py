"""
Risk-Based Approval Routing — Types, Constants, and Helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1

# Category → base risk score
_ACTION_CATEGORY_SCORES: Dict[str, float] = {
    "financial": 0.8,
    "payment": 0.8,
    "destructive": 0.9,
    "delete": 0.9,
    "drop": 0.9,
    "system": 0.7,
    "config": 0.6,
    "write": 0.4,
    "create": 0.3,
    "read": 0.1,
    "safe": 0.1,
    "notification": 0.1,
}

# Role hierarchy level (mirrors auth_parts._imports.ROLE_HIERARCHY)
_ROLE_LEVELS: Dict[str, int] = {
    "viewer": 0,
    "operador": 1,
    "gerente": 2,
    "admin": 3,
}


class RiskLevel(str, Enum):
    """Qualitative risk level."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def _score_to_risk_level(score: float) -> RiskLevel:
    """Map a numeric risk score to a RiskLevel."""
    if score < 0.3:
        return RiskLevel.LOW
    if score < 0.5:
        return RiskLevel.MEDIUM
    if score < 0.7:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


def _score_to_role(score: float) -> str:
    """Map a numeric risk score to the minimum required approver role."""
    if score < 0.3:
        return "auto_approve"
    if score < 0.5:
        return "operador"
    if score < 0.7:
        return "gerente"
    return "admin"


@dataclass
class RiskAssessment:
    """Result of a risk assessment for an approval request."""

    risk_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW
    factors: List[str] = field(default_factory=list)
    recommended_role: str = "auto_approve"
    auto_approvable: bool = True
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "risk_score": round(self.risk_score, 4),
            "risk_level": self.risk_level.value,
            "factors": self.factors,
            "recommended_role": self.recommended_role,
            "auto_approvable": self.auto_approvable,
            "explanation": self.explanation,
        }
