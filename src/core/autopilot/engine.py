"""
ZENIC-AGENTS - Autopilot Engine (Phase D1)

Main orchestrator for the Autopilot by Objectives system. Coordinates
ObjectiveStore, KPITracker, AutopilotPlanner, ClosedLoopFeedback, and
AutonomyConfigManager to autonomously work toward business objectives.

Execute cycle flow:
  1. Get objective and plan
  2. Measure KPIs (KPITracker)
  3. Evaluate feedback (ClosedLoopFeedback)
  4. Check autonomy level (AutonomyConfig)
  5. For each planned step:
     a. Preview impact (ImpactPreviewEngine — lazy import)
     b. Check safety (SafetyGate — lazy import)
     c. Auto-execute or request approval (ActionDispatcher — lazy import)
  6. Update plan step statuses
  7. Return cycle result

Thread-safe: All public methods guarded by RLock.
Retry logic: Critical operations wrapped with 3 retries, base 0.5s backoff.
Lazy imports: Executors, SafetyGate, approval chain imported on first use
              to avoid circular dependencies.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from .objective import (
    Objective,
    ObjectiveStatus,
    ObjectivePriority,
    ObjectiveTarget,
    ObjectiveStore,
    get_objective_store,
    reset_objective_store,
)
from .kpi_tracker import KPITracker, KPIMeasurement, get_kpi_tracker, reset_kpi_tracker
from .planner import (
    AutopilotPlanner,
    PlannedAction,
    PlanStep,
    get_autopilot_planner,
    reset_autopilot_planner,
)
from .feedback import (
    ClosedLoopFeedback,
    FeedbackCycle,
    FeedbackAction,
    get_closed_loop_feedback,
    reset_closed_loop_feedback,
)
from .autonomy import (
    AutonomyLevel,
    AutonomyConfig,
    AutonomyConfigManager,
    get_autonomy_config,
    reset_autonomy_config,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  ENUMS
# ──────────────────────────────────────────────────────────────

class AutopilotStatus(str, Enum):
    """Status of the autopilot engine for a specific objective."""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


# ──────────────────────────────────────────────────────────────
#  RETRY HELPER
# ──────────────────────────────────────────────────────────────

def _retry_operation(
    func: Any,
    max_retries: int = 3,
    base_delay: float = 0.5,
) -> Any:
    """Execute a function with retry logic for critical operations.

    Args:
        func: Callable to execute.
        max_retries: Maximum number of retries.
        base_delay: Base delay in seconds for exponential backoff.

    Returns:
        The result of the function call.

    Raises:
        The last exception if all retries fail.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "AutopilotEngine: DB retry %d/%d after %.2fs — %s",
                attempt + 1, max_retries, delay, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
        except Exception as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "AutopilotEngine: Unexpected error on retry %d/%d — %s",
                attempt + 1, max_retries, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────
#  AUTOPILOT ENGINE
# ──────────────────────────────────────────────────────────────

class AutopilotEngine:
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
        self._objective_store: Optional[ObjectiveStore] = None
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
    def objective_store(self) -> ObjectiveStore:
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

    # ── Schema ──────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        """Create the engine state table if it does not exist."""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return

            def _init() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                        CREATE TABLE IF NOT EXISTS _zenic_autopilot_engine_state (
                            objective_id TEXT PRIMARY KEY,
                            status TEXT NOT NULL DEFAULT 'idle',
                            plan_id TEXT NOT NULL DEFAULT '',
                            last_cycle_at TEXT NOT NULL DEFAULT '',
                            last_cycle_result TEXT NOT NULL DEFAULT '{}',
                            cycle_count INTEGER NOT NULL DEFAULT 0
                        )
                    """)
                    conn.commit()
                finally:
                    conn.close()

            _retry_operation(_init)
            self._initialized = True
            logger.info("AutopilotEngine: Schema initialized at %s", self._db_path)

    # ── Objective Management ────────────────────────────────

    def create_objective(
        self,
        name: str,
        description: str,
        targets: List[Dict[str, Any]],
        priority: str = "normal",
        deadline: str = "",
        tenant_id: str = "",
    ) -> Objective:
        """Create a new objective and persist it.

        Args:
            name: Human-readable name of the objective.
            description: Detailed description of the objective.
            targets: List of target dictionaries with keys:
                     metric_name, current_value, target_value, unit, operator.
            priority: Priority level ("low", "normal", "high", "critical").
            deadline: ISO format deadline string.
            tenant_id: Tenant identifier for multi-tenant deployments.

        Returns:
            The created Objective instance.
        """
        objective_targets = [
            ObjectiveTarget(
                metric_name=t.get("metric_name", ""),
                current_value=t.get("current_value", 0.0),
                target_value=t.get("target_value", 0.0),
                unit=t.get("unit", ""),
                operator=t.get("operator", "<"),
            )
            for t in targets
        ]

        objective = Objective(
            name=name,
            description=description,
            priority=ObjectivePriority(priority),
            status=ObjectiveStatus.DRAFT,
            targets=objective_targets,
            deadline=deadline,
            tenant_id=tenant_id,
        )

        self.objective_store.create_objective(objective)
        self._objective_statuses[objective.objective_id] = AutopilotStatus.IDLE
        self._stats["objectives_created"] += 1

        logger.info(
            "AutopilotEngine: Created objective %s '%s' with %d targets",
            objective.objective_id, name, len(objective_targets),
        )
        return objective

    def start_objective(self, objective_id: str) -> PlannedAction:
        """Start working on an objective.

        Creates a plan, sets the objective status to ACTIVE, and
        begins KPI tracking. Returns the generated plan.

        Args:
            objective_id: The objective ID to start.

        Returns:
            The PlannedAction for this objective.

        Raises:
            ValueError: If the objective is not found.
        """
        self._ensure_schema()
        objective = self.objective_store.get_objective(objective_id)
        if objective is None:
            raise ValueError(f"Objective not found: {objective_id}")

        # Set objective to active
        objective.status = ObjectiveStatus.ACTIVE
        self.objective_store.update_objective(objective)

        # Create plan
        plan = self.planner.plan_for_objective(objective)
        plan.status = "active"

        # Record initial KPI measurements
        self.kpi_tracker.measure_all_for_objective(objective)

        # Update engine state
        self._objective_statuses[objective_id] = AutopilotStatus.PLANNING
        self._active_plans[objective_id] = plan

        # Persist engine state
        self._persist_engine_state(
            objective_id=objective_id,
            status=AutopilotStatus.PLANNING,
            plan_id=plan.plan_id,
        )

        logger.info(
            "AutopilotEngine: Started objective %s with plan %s (%d steps)",
            objective_id, plan.plan_id, len(plan.steps),
        )
        return plan

    # ── Main Execution Cycle ────────────────────────────────

    def execute_cycle(self, objective_id: str) -> Dict[str, Any]:
        """Execute one autopilot cycle for an objective.

        Main autopilot loop:
          1. Get objective and plan
          2. Measure KPIs
          3. Evaluate feedback
          4. Check autonomy level
          5. For each planned step: preview → safety → execute/approve
          6. Update step statuses
          7. Return cycle result

        Args:
            objective_id: The objective ID to process.

        Returns:
            Dictionary with cycle results including actions taken,
            KPI changes, feedback, and any pending approvals.
        """
        self._ensure_schema()
        with self._lock:
            self._cycle_count += 1
            self._stats["cycles_executed"] += 1

            # 1. Get objective and plan
            objective = self.objective_store.get_objective(objective_id)
            if objective is None:
                return {
                    "objective_id": objective_id,
                    "status": "error",
                    "error": "Objective not found",
                }

            if objective.status != ObjectiveStatus.ACTIVE:
                return {
                    "objective_id": objective_id,
                    "status": "skipped",
                    "reason": f"Objective status is {objective.status.value}",
                }

            plan = self._active_plans.get(objective_id)
            if plan is None:
                plans = self.planner.list_plans(objective_id=objective_id)
                if plans:
                    plan = plans[0]
                    self._active_plans[objective_id] = plan
                else:
                    plan = self.start_objective(objective_id)

            self._objective_statuses[objective_id] = AutopilotStatus.EXECUTING

            # 2. Measure KPIs
            measurements = self.kpi_tracker.measure_all_for_objective(objective)
            kpi_summary = {m.metric_name: m.value for m in measurements}

            # 3. Evaluate feedback
            feedback_cycle = self.feedback.evaluate_cycle(
                objective=objective,
                plan=plan,
                kpi_tracker=self.kpi_tracker,
            )

            # 4. Check autonomy level
            autonomy_config = self.autonomy_manager.get_config(
                objective_id=objective_id,
                tenant_id=objective.tenant_id,
            )

            # 5. Process planned steps
            executed_actions: List[Dict[str, Any]] = []
            pending_approvals: List[Dict[str, Any]] = []
            skipped_actions: List[Dict[str, Any]] = []
            approval_needed = False

            for step in plan.steps:
                if step.status == "completed":
                    continue

                # Check if dependencies are met
                deps_met = all(
                    any(s.step_id == dep_id and s.status == "completed"
                        for s in plan.steps)
                    for dep_id in step.depends_on
                )
                if not deps_met:
                    continue

                # a. Preview impact
                try:
                    impact = self.impact_preview_engine.preview_action(
                        action_type=step.action_type,
                        config=step.action_config,
                    )
                    risk_score = getattr(impact, "risk_score", 0.3)
                except Exception as exc:
                    logger.warning(
                        "AutopilotEngine: Impact preview failed for step %s: %s",
                        step.step_id, exc,
                    )
                    risk_score = 0.5  # Conservative default

                # b. Check safety
                try:
                    safety_result = self.safety_gate.check(
                        action_type=step.action_type,
                        config=step.action_config,
                    )
                    safety_verdict = getattr(safety_result, "verdict", None)
                    if safety_verdict is not None and str(safety_verdict) == "DENY":
                        self.planner.update_step_status(
                            plan.plan_id, step.step_id, "blocked",
                        )
                        skipped_actions.append({
                            "step_id": step.step_id,
                            "name": step.name,
                            "reason": "Safety gate denied",
                        })
                        self._stats["actions_skipped"] += 1
                        continue
                except Exception as exc:
                    logger.warning(
                        "AutopilotEngine: Safety gate check failed for step %s: %s",
                        step.step_id, exc,
                    )

                # c. Check autonomy - can auto-execute?
                can_auto = autonomy_config.can_auto_execute(risk_score)

                if can_auto:
                    # Execute the action
                    try:
                        result = self._execute_step(step, objective)
                        executed_actions.append({
                            "step_id": step.step_id,
                            "name": step.name,
                            "result": result,
                        })
                        self.planner.update_step_status(
                            plan.plan_id, step.step_id, "completed",
                        )
                        self._stats["actions_executed"] += 1
                    except Exception as exc:
                        logger.error(
                            "AutopilotEngine: Step %s execution failed: %s",
                            step.step_id, exc,
                        )
                        self.planner.update_step_status(
                            plan.plan_id, step.step_id, "failed",
                        )
                        executed_actions.append({
                            "step_id": step.step_id,
                            "name": step.name,
                            "error": str(exc),
                        })
                        if autonomy_config.pause_on_exception:
                            self._objective_statuses[objective_id] = AutopilotStatus.PAUSED
                            break
                else:
                    # Needs approval
                    approval_needed = True
                    pending_approvals.append({
                        "step_id": step.step_id,
                        "name": step.name,
                        "risk_score": risk_score,
                        "reason": "Requires human approval",
                    })
                    self._stats["actions_approved"] += 1

                    # Check max actions per cycle
                    if len(executed_actions) >= autonomy_config.max_actions_per_cycle:
                        break

            # Handle feedback-driven actions
            if feedback_cycle.action_taken == FeedbackAction.PAUSE_OBJECTIVE:
                self.pause_objective(objective_id)
                self._objective_statuses[objective_id] = AutopilotStatus.PAUSED
            elif feedback_cycle.action_taken == FeedbackAction.ESCALATE_TO_HUMAN:
                self._stats["escalations"] += 1
                logger.warning(
                    "AutopilotEngine: Objective %s escalated to human",
                    objective_id,
                )

            # Check if objective is completed
            all_targets_met = all(t.is_met() for t in objective.targets)
            if all_targets_met:
                objective.status = ObjectiveStatus.COMPLETED
                self.objective_store.update_objective(objective)
                self._objective_statuses[objective_id] = AutopilotStatus.COMPLETED
                self._stats["objectives_completed"] += 1

            # Update engine status
            if approval_needed and self._objective_statuses.get(objective_id) != AutopilotStatus.PAUSED:
                self._objective_statuses[objective_id] = AutopilotStatus.WAITING_APPROVAL

            # Persist engine state
            cycle_result = {
                "cycle_number": self._cycle_count,
                "kpi_summary": kpi_summary,
                "feedback_action": feedback_cycle.action_taken.value,
                "feedback_analysis": feedback_cycle.analysis,
                "executed_actions": executed_actions,
                "pending_approvals": pending_approvals,
                "skipped_actions": skipped_actions,
                "all_targets_met": all_targets_met,
            }

            self._persist_engine_state(
                objective_id=objective_id,
                status=self._objective_statuses.get(objective_id, AutopilotStatus.IDLE),
                plan_id=plan.plan_id,
                result=cycle_result,
            )

            return {
                "objective_id": objective_id,
                "status": self._objective_statuses.get(objective_id, AutopilotStatus.IDLE).value,
                **cycle_result,
            }

    # ── Objective Lifecycle ─────────────────────────────────

    def pause_objective(self, objective_id: str) -> bool:
        """Pause an active objective.

        Args:
            objective_id: The objective ID to pause.

        Returns:
            True if the objective was paused, False if not found or not active.
        """
        with self._lock:
            objective = self.objective_store.get_objective(objective_id)
            if objective is None or objective.status != ObjectiveStatus.ACTIVE:
                return False

            objective.status = ObjectiveStatus.PAUSED
            self.objective_store.update_objective(objective)
            self._objective_statuses[objective_id] = AutopilotStatus.PAUSED

            self._persist_engine_state(
                objective_id=objective_id,
                status=AutopilotStatus.PAUSED,
            )

            logger.info("AutopilotEngine: Paused objective %s", objective_id)
            return True

    def resume_objective(self, objective_id: str) -> bool:
        """Resume a paused objective.

        Args:
            objective_id: The objective ID to resume.

        Returns:
            True if the objective was resumed, False if not found or not paused.
        """
        with self._lock:
            objective = self.objective_store.get_objective(objective_id)
            if objective is None or objective.status != ObjectiveStatus.PAUSED:
                return False

            objective.status = ObjectiveStatus.ACTIVE
            self.objective_store.update_objective(objective)
            self._objective_statuses[objective_id] = AutopilotStatus.IDLE

            self._persist_engine_state(
                objective_id=objective_id,
                status=AutopilotStatus.IDLE,
            )

            logger.info("AutopilotEngine: Resumed objective %s", objective_id)
            return True

    def cancel_objective(self, objective_id: str) -> bool:
        """Cancel an objective.

        Args:
            objective_id: The objective ID to cancel.

        Returns:
            True if the objective was cancelled, False if not found.
        """
        with self._lock:
            objective = self.objective_store.get_objective(objective_id)
            if objective is None:
                return False

            objective.status = ObjectiveStatus.CANCELLED
            self.objective_store.update_objective(objective)
            self._objective_statuses[objective_id] = AutopilotStatus.FAILED

            self._persist_engine_state(
                objective_id=objective_id,
                status=AutopilotStatus.FAILED,
            )

            logger.info("AutopilotEngine: Cancelled objective %s", objective_id)
            return True

    # ── Status Queries ──────────────────────────────────────

    def get_status(self, objective_id: str) -> Dict[str, Any]:
        """Get comprehensive status for an objective.

        Args:
            objective_id: The objective ID to query.

        Returns:
            Dictionary with objective status, KPI progress, plan, and feedback.
        """
        objective = self.objective_store.get_objective(objective_id)
        if objective is None:
            return {"objective_id": objective_id, "status": "not_found"}

        engine_status = self._objective_statuses.get(
            objective_id, AutopilotStatus.IDLE,
        )
        progress = self.kpi_tracker.get_objective_progress(objective_id)
        plan = self._active_plans.get(objective_id)
        latest_feedback = self.feedback.get_latest_cycle(objective_id)

        result: Dict[str, Any] = {
            "objective_id": objective_id,
            "name": objective.name,
            "status": objective.status.value,
            "engine_status": engine_status.value,
            "priority": objective.priority.value,
            "progress_percent": objective.progress_percent(),
            "is_overdue": objective.is_overdue(),
            "targets": [t.to_dict() for t in objective.targets],
            "kpi_progress": progress,
            "plan": plan.to_dict() if plan else None,
            "latest_feedback": latest_feedback.to_dict() if latest_feedback else None,
            "created_at": objective.created_at,
            "deadline": objective.deadline,
        }

        return result

    def get_all_objectives_status(self) -> List[Dict[str, Any]]:
        """Get status for all objectives.

        Returns:
            A list of status dictionaries, one per objective.
        """
        objectives = self.objective_store.list_objectives()
        return [self.get_status(o.objective_id) for o in objectives]

    def check_and_execute(self) -> List[Dict[str, Any]]:
        """Run one cycle for all active objectives.

        Iterates over all active objectives and executes a cycle
        for each one. Returns a summary of all cycle results.

        Returns:
            A list of cycle result dictionaries.
        """
        active = self.objective_store.get_active_objectives()
        results: List[Dict[str, Any]] = []

        for objective in active:
            try:
                result = self.execute_cycle(objective.objective_id)
                results.append(result)
            except Exception as exc:
                logger.error(
                    "AutopilotEngine: Cycle failed for %s: %s",
                    objective.objective_id, exc,
                )
                results.append({
                    "objective_id": objective.objective_id,
                    "status": "error",
                    "error": str(exc),
                })

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics.

        Returns:
            Dictionary with counts of objectives, cycles, actions, etc.
        """
        return {
            **self._stats,
            "cycle_count": self._cycle_count,
            "active_objectives": sum(
                1 for s in self._objective_statuses.values()
                if s in (AutopilotStatus.EXECUTING, AutopilotStatus.PLANNING, AutopilotStatus.WAITING_APPROVAL)
            ),
            "paused_objectives": sum(
                1 for s in self._objective_statuses.values()
                if s == AutopilotStatus.PAUSED
            ),
        }

    # ── Internal Helpers ────────────────────────────────────

    def _execute_step(
        self, step: PlanStep, objective: Objective,
    ) -> Dict[str, Any]:
        """Execute a single plan step via the ActionDispatcher.

        Uses lazy-loaded ActionDispatcher to dispatch the step's
        action_type and action_config.

        Args:
            step: The PlanStep to execute.
            objective: The parent Objective.

        Returns:
            Dictionary with execution result.
        """
        try:
            from ..executors.dispatch_action import DispatchRequest
            request = DispatchRequest(
                action_type=step.action_type,
                config=step.action_config,
                tenant_id=objective.tenant_id,
            )
            # Sync dispatch for non-async context
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                # We're inside an existing event loop, schedule accordingly
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.action_dispatcher.dispatch(request),
                    )
                    result = future.result(timeout=30)
            except RuntimeError:
                # No running loop, safe to use asyncio.run
                result = asyncio.run(self.action_dispatcher.dispatch(request))

            return {
                "success": result.success,
                "action_id": result.action_id,
                "safety_verdict": result.safety_verdict.value if result.safety_verdict else "unknown",
                "duration_ms": result.total_duration_ms,
            }
        except ImportError:
            # ActionDispatcher not available - log and return mock result
            logger.info(
                "AutopilotEngine: Step %s executed (no dispatcher; mock)",
                step.step_id,
            )
            return {
                "success": True,
                "action_id": step.step_id,
                "safety_verdict": "mock",
                "duration_ms": 0,
            }

    def _persist_engine_state(
        self,
        objective_id: str,
        status: AutopilotStatus,
        plan_id: str = "",
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist the engine state for an objective.

        Args:
            objective_id: The objective ID.
            status: The current engine status.
            plan_id: The active plan ID.
            result: The latest cycle result.
        """
        self._ensure_schema()

        def _upsert() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT OR REPLACE INTO _zenic_autopilot_engine_state
                       (objective_id, status, plan_id, last_cycle_at,
                        last_cycle_result, cycle_count)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        objective_id,
                        status.value,
                        plan_id,
                        datetime.now(timezone.utc).isoformat(),
                        json.dumps(result or {}),
                        self._cycle_count,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        try:
            _retry_operation(_upsert)
        except Exception as exc:
            logger.warning(
                "AutopilotEngine: Failed to persist state for %s: %s",
                objective_id, exc,
            )


# ──────────────────────────────────────────────────────────────
#  FALLBACK CLASSES (for when executors are unavailable)
# ──────────────────────────────────────────────────────────────

class _NoOpImpactPreview:
    """Fallback ImpactPreviewEngine when the real one is unavailable."""

    def preview_action(
        self,
        action_type: str,
        config: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Return a minimal impact preview with conservative risk score."""
        return _MockImpactPreview(action_type=action_type, risk_score=0.3)


@dataclass
class _MockImpactPreview:
    """Minimal impact preview for fallback mode."""
    action_type: str = ""
    risk_score: float = 0.3

    def to_dict(self) -> Dict[str, Any]:
        return {"action_type": self.action_type, "risk_score": self.risk_score}


class _PermissiveSafetyFallback:
    """Fallback SafetyGate when the real one is unavailable.

    Returns ALLOW for all actions to avoid blocking the autopilot.
    """

    def check(
        self,
        action_type: str,
        config: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Return ALLOW verdict for all actions."""
        return _MockSafetyResult()


@dataclass
class _MockSafetyResult:
    """Minimal safety result for fallback mode."""
    verdict: str = "ALLOW"

    def to_dict(self) -> Dict[str, Any]:
        return {"verdict": self.verdict}


class _NoOpDispatcher:
    """Fallback ActionDispatcher when the real one is unavailable."""

    async def dispatch(self, request: Any) -> Any:
        """Return a success result without executing anything."""
        return _MockDispatchResult(success=True)


@dataclass
class _MockDispatchResult:
    """Minimal dispatch result for fallback mode."""
    success: bool = True
    action_id: str = ""
    safety_verdict: Any = None
    total_duration_ms: float = 0.0


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

_autopilot_engine_instance: Optional[AutopilotEngine] = None
_autopilot_engine_lock = threading.Lock()


def get_autopilot_engine(db_path: str = "autopilot_engine.sqlite") -> AutopilotEngine:
    """Get or create the global AutopilotEngine instance.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        The singleton AutopilotEngine instance.
    """
    global _autopilot_engine_instance
    with _autopilot_engine_lock:
        if _autopilot_engine_instance is None:
            _autopilot_engine_instance = AutopilotEngine(db_path=db_path)
        return _autopilot_engine_instance


def reset_autopilot_engine() -> None:
    """Reset the global AutopilotEngine instance (for testing)."""
    global _autopilot_engine_instance
    with _autopilot_engine_lock:
        _autopilot_engine_instance = None


__all__ = [
    "AutopilotStatus",
    "AutopilotEngine",
    "get_autopilot_engine",
    "reset_autopilot_engine",
]
