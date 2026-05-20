"""
Zenic-Agents Asistente - Risk-Based Approval Routing (Phase C3)

Routes approval requests based on a contextual risk score computed from
multiple factors: action category, monetary amount, target environment,
time of day, and user history.
"""

from ._types import (
    RiskLevel,
    RiskAssessment,
    _ACTION_CATEGORY_SCORES,
    _ROLE_LEVELS,
    _MAX_RETRIES,
    _RETRY_DELAY,
    _score_to_risk_level,
    _score_to_role,
)
from ._mixin_core import RiskBasedApprovalRouter

# ── Singleton ─────────────────────────────────────────────

import threading
from typing import Optional

_risk_router_instance: Optional[RiskBasedApprovalRouter] = None
_risk_router_lock = threading.Lock()


def get_risk_router(db_path: str = "risk_routing.sqlite") -> RiskBasedApprovalRouter:
    """Get or create the global RiskBasedApprovalRouter instance."""
    global _risk_router_instance
    with _risk_router_lock:
        if _risk_router_instance is None:
            _risk_router_instance = RiskBasedApprovalRouter(db_path=db_path)
        return _risk_router_instance


def reset_risk_router() -> None:
    """Reset the global RiskBasedApprovalRouter (for testing)."""
    global _risk_router_instance
    _risk_router_instance = None


__all__ = [
    "RiskLevel",
    "RiskAssessment",
    "RiskBasedApprovalRouter",
    "get_risk_router",
    "reset_risk_router",
]
