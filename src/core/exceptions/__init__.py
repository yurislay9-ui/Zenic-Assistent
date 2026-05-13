"""
Zenic-Agents - Exception Engine Package (Phase C2)

Unified exception handling, routing, and analytics subsystem.

Architecture:
  taxonomy   → Exception category/severity enums, context, helpers
  engine     → ExceptionEngine (signal creation, persistence, auto-brake)
  routing    → ExceptionRouter (rule-based action mapping)
  analytics  → ExceptionAnalytics (pattern detection, dashboards)

Usage:
    from src.core.exceptions import get_exception_engine

    engine = get_exception_engine()
    sig = engine.signal("my_source", ExceptionCategory.TIMEOUT,
                        ExceptionSeverity.ERROR, "Connection timed out")

Graceful degradation: if any submodule fails to import, a warning is
logged and the corresponding exports are set to ``None`` so that the
rest of the package remains usable.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── taxonomy ──────────────────────────────────────────────────

try:
    from .taxonomy import (
        ExceptionCategory,
        ExceptionSeverity,
        ZenicException,
        ExceptionContext,
    )
except ImportError as exc:
    logger.warning("exceptions: failed to import taxonomy submodule: %s", exc)
    ExceptionCategory = None  # type: ignore[assignment,misc]
    ExceptionSeverity = None  # type: ignore[assignment,misc]
    ZenicException = None  # type: ignore[assignment,misc]
    ExceptionContext = None  # type: ignore[assignment,misc]

# ── engine ────────────────────────────────────────────────────

try:
    from .engine import (
        ExceptionEngine,
        ExceptionSignal,
        ExceptionRecord,
        get_exception_engine,
        reset_exception_engine,
    )
except ImportError as exc:
    logger.warning("exceptions: failed to import engine submodule: %s", exc)
    ExceptionEngine = None  # type: ignore[assignment,misc]
    ExceptionSignal = None  # type: ignore[assignment,misc]
    ExceptionRecord = None  # type: ignore[assignment,misc]
    get_exception_engine = None  # type: ignore[assignment,misc]
    reset_exception_engine = None  # type: ignore[assignment,misc]

# ── routing ───────────────────────────────────────────────────

try:
    from .routing import (
        ExceptionRouter,
        RoutingRule,
        RoutingAction,
        get_exception_router,
        reset_exception_router,
    )
except ImportError as exc:
    logger.warning("exceptions: failed to import routing submodule: %s", exc)
    ExceptionRouter = None  # type: ignore[assignment,misc]
    RoutingRule = None  # type: ignore[assignment,misc]
    RoutingAction = None  # type: ignore[assignment,misc]
    get_exception_router = None  # type: ignore[assignment,misc]
    reset_exception_router = None  # type: ignore[assignment,misc]

# ── analytics ─────────────────────────────────────────────────

try:
    from .analytics import (
        ExceptionAnalytics,
        ExceptionPattern,
        AnalyticsSnapshot,
        get_exception_analytics,
        reset_exception_analytics,
    )
except ImportError as exc:
    logger.warning("exceptions: failed to import analytics submodule: %s", exc)
    ExceptionAnalytics = None  # type: ignore[assignment,misc]
    ExceptionPattern = None  # type: ignore[assignment,misc]
    AnalyticsSnapshot = None  # type: ignore[assignment,misc]
    get_exception_analytics = None  # type: ignore[assignment,misc]
    reset_exception_analytics = None  # type: ignore[assignment,misc]


# ── Public API ────────────────────────────────────────────────

__all__ = [
    # taxonomy
    "ExceptionCategory",
    "ExceptionSeverity",
    "ZenicException",
    "ExceptionContext",
    # engine
    "ExceptionEngine",
    "ExceptionSignal",
    "ExceptionRecord",
    "get_exception_engine",
    "reset_exception_engine",
    # routing
    "ExceptionRouter",
    "RoutingRule",
    "RoutingAction",
    "get_exception_router",
    "reset_exception_router",
    # analytics
    "ExceptionAnalytics",
    "ExceptionPattern",
    "AnalyticsSnapshot",
    "get_exception_analytics",
    "reset_exception_analytics",
]
