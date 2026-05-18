"""ZENIC-AGENTS - Autopilot Engine

Orchestrates the autonomous agent lifecycle.

The AutopilotEngine class is composed from several mixins that each
provide a coherent group of methods:

- _PersistenceMixin  → schema init & state persistence
- _LifecycleMixin    → create / start / pause / resume / cancel objectives
- _ExecutionMixin    → execute_cycle & _execute_step
- _QueriesMixin      → status queries & statistics

This file defines the main class with __init__, lazy-loaded subsystem
properties, and the public __all__ re-exports.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

# ── Re-exports from extracted modules ──────────────────────
from ._status import AutopilotStatus
from ._singleton import get_autopilot_engine, reset_autopilot_engine
from ._retry import _retry_operation
from ._fallbacks import (
    _NoOpImpactPreview,
    _MockImpactPreview,
    _PermissiveSafetyFallback,
    _MockSafetyResult,
    _NoOpDispatcher,
    _MockDispatchResult,
)
from ._persistence import _PersistenceMixin
from ._lifecycle import _LifecycleMixin
from ._execution import _ExecutionMixin
from ._queries import _QueriesMixin

# ── Subsystem imports for lazy-load helpers ────────────────
from src.core.autopilot.objective import (
    Objective,
    get_objective_store,
)
from src.core.autopilot.kpi_tracker import KPITracker, get_kpi_tracker
from src.core.autopilot.planner import AutopilotPlanner, PlannedAction, get_autopilot_planner
from src.core.autopilot.feedback import ClosedLoopFeedback, get_closed_loop_feedback
from src.core.autopilot.autonomy import AutonomyConfigManager, get_autonomy_config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  AUTOPILOT ENGINE
# ──────────────────────────────────────────────────────────────

class AutopilotEngine(
    _PersistenceMixin,
    _LifecycleMixin,
    _ExecutionMixin,
    _QueriesMixin,
):
    """Main orchestrator for the Autopilot by Objectives system.

    Coordinates all subsystems (ObjectiveStore, KPITracker, Planner,
    Feedback, AutonomyConfig) and provides the main execute_cycle()
    method that drives the autopilot loop.

    Lazy-loads executor subsystems (ImpactPreviewEngine, SafetyGate,
    ActionDispatcher) on first use to avoid circular dependencies.

    Thread-safe: All public methods guarded by RLock.
    """

    def __init__(self, db_path: str = "autopilot_engine.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._initialized = False

        # Lazy-loaded subsystems
        self._objective_store: Optional[Any] = None
        self._kpi_tracker: Optional[KPITracker] = None
        self._planner: Optional[AutopilotPlanner] = None
        self._feedback: Optional[ClosedLoopFeedback] = None
        self._autonomy_manager: Optional[AutonomyConfigManager] = None

        # Lazy-loaded executor subsystems (avoid circular imports)
        self._impact_preview_engine: Any = None
        self._safety_gate: Any = None
        self._action_dispatcher: Any = None

        # Engine state tracking
        self._objective_statuses: Dict[str, AutopilotStatus] = {}
        self._active_plans: Dict[str, PlannedAction] = {}
        self._cycle_count: int = 0
        self._stats = {
            "objectives_created": 0,
            "cycles_executed": 0,
            "actions_executed": 0,
            "actions_approved": 0,
            "actions_skipped": 0,
            "objectives_completed": 0,
            "objectives_failed": 0,
            "escalations": 0,
        }

    # ── Lazy-Loaded Subsystems ──────────────────────────────

    @property
    def objective_store(self) -> Any:
        """Lazy-load ObjectiveStore."""
        if self._objective_store is None:
            self._objective_store = get_objective_store()
        return self._objective_store

    @property
    def kpi_tracker(self) -> KPITracker:
        """Lazy-load KPITracker."""
        if self._kpi_tracker is None:
            self._kpi_tracker = get_kpi_tracker()
        return self._kpi_tracker

    @property
    def planner(self) -> AutopilotPlanner:
        """Lazy-load AutopilotPlanner."""
        if self._planner is None:
            self._planner = get_autopilot_planner()
        return self._planner

    @property
    def feedback(self) -> ClosedLoopFeedback:
        """Lazy-load ClosedLoopFeedback."""
        if self._feedback is None:
            self._feedback = get_closed_loop_feedback()
        return self._feedback

    @property
    def autonomy_manager(self) -> AutonomyConfigManager:
        """Lazy-load AutonomyConfigManager."""
        if self._autonomy_manager is None:
            self._autonomy_manager = get_autonomy_config()
        return self._autonomy_manager

    @property
    def impact_preview_engine(self) -> Any:
        """Lazy-load ImpactPreviewEngine (avoids circular imports)."""
        if self._impact_preview_engine is None:
            try:
                from ..executors.impact_preview import get_impact_preview_engine
                self._impact_preview_engine = get_impact_preview_engine()
            except ImportError:
                logger.warning(
                    "AutopilotEngine: ImpactPreviewEngine not available; using no-op fallback",
                )
                self._impact_preview_engine = _NoOpImpactPreview()
        return self._impact_preview_engine

    @property
    def safety_gate(self) -> Any:
        """Lazy-load SafetyGate (avoids circular imports)."""
        if self._safety_gate is None:
            try:
                from ..executors.safety_gate import get_default_safety_gate
                self._safety_gate = get_default_safety_gate()
            except ImportError:
                logger.warning(
                    "AutopilotEngine: SafetyGate not available; using permissive fallback",
                )
                self._safety_gate = _PermissiveSafetyFallback()
        return self._safety_gate

    @property
    def action_dispatcher(self) -> Any:
        """Lazy-load ActionDispatcher (avoids circular imports)."""
        if self._action_dispatcher is None:
            try:
                from ..executors.dispatch_action import get_default_dispatcher
                self._action_dispatcher = get_default_dispatcher()
            except ImportError:
                logger.warning(
                    "AutopilotEngine: ActionDispatcher not available; using no-op fallback",
                )
                self._action_dispatcher = _NoOpDispatcher()
        return self._action_dispatcher


__all__ = ["AutopilotStatus", "AutopilotEngine", "get_autopilot_engine", "reset_autopilot_engine"]
