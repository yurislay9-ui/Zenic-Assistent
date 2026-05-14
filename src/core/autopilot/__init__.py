"""
ZENIC-AGENTS - Autopilot by Objectives Package (Phase D1)

Autonomous objective-driven automation system for business goals.
Coordinates planning, KPI tracking, feedback loops, and autonomy
management to work toward objectives like "reduce overdue invoices to <5%".

Components:
  - Objective: Business goal with measurable targets
  - KPITracker: Measurement and trend analysis
  - AutopilotPlanner: Decomposes objectives into actionable steps
  - ClosedLoopFeedback: Measures results and adjusts strategy
  - AutonomyConfig: Controls auto-execution vs. human approval
  - AutopilotEngine: Main orchestrator tying everything together

Graceful degradation: Import failures are caught so that partial
availability of executor subsystems (SafetyGate, ActionDispatcher)
does not prevent the core autopilot from functioning.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Objective ─────────────────────────────────────────────────
try:
    from .objective import (
        Objective,
        ObjectiveStatus,
        ObjectivePriority,
        ObjectiveTarget,
        get_objective_store,
        reset_objective_store,
    )
except ImportError as exc:
    logger.warning("Autopilot: Failed to import objective module: %s", exc)
    Objective = None  # type: ignore[assignment, misc]
    ObjectiveStatus = None  # type: ignore[assignment, misc]
    ObjectivePriority = None  # type: ignore[assignment, misc]
    ObjectiveTarget = None  # type: ignore[assignment, misc]
    get_objective_store = None  # type: ignore[assignment]
    reset_objective_store = None  # type: ignore[assignment]

# ── KPI Tracker ───────────────────────────────────────────────
try:
    from .kpi_tracker import (
        KPITracker,
        KPIMeasurement,
        KPITrend,
        get_kpi_tracker,
        reset_kpi_tracker,
    )
except ImportError as exc:
    logger.warning("Autopilot: Failed to import kpi_tracker module: %s", exc)
    KPITracker = None  # type: ignore[assignment, misc]
    KPIMeasurement = None  # type: ignore[assignment, misc]
    KPITrend = None  # type: ignore[assignment, misc]
    get_kpi_tracker = None  # type: ignore[assignment]
    reset_kpi_tracker = None  # type: ignore[assignment]

# ── Planner ───────────────────────────────────────────────────
try:
    from .planner import (
        AutopilotPlanner,
        PlannedAction,
        PlanStep,
        get_autopilot_planner,
        reset_autopilot_planner,
    )
except ImportError as exc:
    logger.warning("Autopilot: Failed to import planner module: %s", exc)
    AutopilotPlanner = None  # type: ignore[assignment, misc]
    PlannedAction = None  # type: ignore[assignment, misc]
    PlanStep = None  # type: ignore[assignment, misc]
    get_autopilot_planner = None  # type: ignore[assignment]
    reset_autopilot_planner = None  # type: ignore[assignment]

# ── Feedback ──────────────────────────────────────────────────
try:
    from .feedback import (
        ClosedLoopFeedback,
        FeedbackCycle,
        FeedbackAction,
        get_closed_loop_feedback,
        reset_closed_loop_feedback,
    )
except ImportError as exc:
    logger.warning("Autopilot: Failed to import feedback module: %s", exc)
    ClosedLoopFeedback = None  # type: ignore[assignment, misc]
    FeedbackCycle = None  # type: ignore[assignment, misc]
    FeedbackAction = None  # type: ignore[assignment, misc]
    get_closed_loop_feedback = None  # type: ignore[assignment]
    reset_closed_loop_feedback = None  # type: ignore[assignment]

# ── Autonomy ──────────────────────────────────────────────────
try:
    from .autonomy import (
        AutonomyLevel,
        AutonomyConfig,
        get_autonomy_config,
        reset_autonomy_config,
    )
except ImportError as exc:
    logger.warning("Autopilot: Failed to import autonomy module: %s", exc)
    AutonomyLevel = None  # type: ignore[assignment, misc]
    AutonomyConfig = None  # type: ignore[assignment, misc]
    get_autonomy_config = None  # type: ignore[assignment]
    reset_autonomy_config = None  # type: ignore[assignment]

# ── Engine ────────────────────────────────────────────────────
try:
    from .engine import (
        AutopilotEngine,
        AutopilotStatus,
        get_autopilot_engine,
        reset_autopilot_engine,
    )
except ImportError as exc:
    logger.warning("Autopilot: Failed to import engine module: %s", exc)
    AutopilotEngine = None  # type: ignore[assignment, misc]
    AutopilotStatus = None  # type: ignore[assignment, misc]
    get_autopilot_engine = None  # type: ignore[assignment]
    reset_autopilot_engine = None  # type: ignore[assignment]


__all__ = [
    # Objective
    "Objective",
    "ObjectiveStatus",
    "ObjectivePriority",
    "ObjectiveTarget",
    "get_objective_store",
    "reset_objective_store",
    # KPI Tracker
    "KPITracker",
    "KPIMeasurement",
    "KPITrend",
    "get_kpi_tracker",
    "reset_kpi_tracker",
    # Planner
    "AutopilotPlanner",
    "PlannedAction",
    "PlanStep",
    "get_autopilot_planner",
    "reset_autopilot_planner",
    # Feedback
    "ClosedLoopFeedback",
    "FeedbackCycle",
    "FeedbackAction",
    "get_closed_loop_feedback",
    "reset_closed_loop_feedback",
    # Autonomy
    "AutonomyLevel",
    "AutonomyConfig",
    "get_autonomy_config",
    "reset_autonomy_config",
    # Engine
    "AutopilotEngine",
    "AutopilotStatus",
    "get_autopilot_engine",
    "reset_autopilot_engine",
]
