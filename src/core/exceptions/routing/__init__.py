"""
Zenic-Agents - Exception Router (Phase C2)

Routes exception signals to appropriate actions based on configurable
rules.  Provides SQLite-persisted routing rules with thread safety,
retry logic, and lazy integration with ApprovalChain, AutomationEngine,
and DegradedModeManager to avoid circular imports.
"""

from __future__ import annotations

from ._router import (
    ExceptionRouterBase,
    RoutingAction,
    RoutingRule,
    get_exception_router,
    reset_exception_router,
)
from ._handlers import ExceptionRouterHandlersMixin


class ExceptionRouter(ExceptionRouterBase, ExceptionRouterHandlersMixin):
    """Maps exception signals to actions based on configurable rules.

    Combines core routing logic with action handlers.

    Features:
        - SQLite persistence for routing rules
        - Thread-safe operations
        - Rule matching by category + severity range + extra conditions
        - Lazy integration with ApprovalChain, AutomationEngine,
          and DegradedModeManager (avoids circular imports)
        - Sensible default rules via :meth:`load_default_rules`
    """


__all__ = [
    "RoutingAction",
    "RoutingRule",
    "ExceptionRouter",
    "get_exception_router",
    "reset_exception_router",
]
