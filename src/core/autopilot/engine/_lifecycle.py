"""ZENIC-AGENTS - Autopilot Engine: Lifecycle Mixin

Provides objective lifecycle management methods (create, start,
pause, resume, cancel) for the AutopilotEngine class.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ._status import AutopilotStatus

from src.core.autopilot.objective import (
    Objective,
    ObjectiveTarget,
    ObjectivePriority,
    ObjectiveStatus,
    get_objective_store,
)
from src.core.autopilot.planner import AutopilotPlanner, PlannedAction, get_autopilot_planner
from src.core.autopilot.kpi_tracker import KPITracker, get_kpi_tracker

logger = logging.getLogger(__name__)


class _LifecycleMixin:
    """Mixin providing objective lifecycle methods for AutopilotEngine."""

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

        self.objective_store.create_objective(objective)  # type: ignore[attr-defined]
        self._objective_statuses[objective.objective_id] = AutopilotStatus.IDLE  # type: ignore[attr-defined]
        self._stats["objectives_created"] += 1  # type: ignore[attr-defined]

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
        self._ensure_schema()  # type: ignore[attr-defined]
        objective = self.objective_store.get_objective(objective_id)  # type: ignore[attr-defined]
        if objective is None:
            raise ValueError(f"Objective not found: {objective_id}")

        # Set objective to active
        objective.status = ObjectiveStatus.ACTIVE
        self.objective_store.update_objective(objective)  # type: ignore[attr-defined]

        # Create plan
        plan = self.planner.plan_for_objective(objective)  # type: ignore[attr-defined]
        plan.status = "active"

        # Record initial KPI measurements
        self.kpi_tracker.measure_all_for_objective(objective)  # type: ignore[attr-defined]

        # Update engine state
        self._objective_statuses[objective_id] = AutopilotStatus.PLANNING  # type: ignore[attr-defined]
        self._active_plans[objective_id] = plan  # type: ignore[attr-defined]

        # Persist engine state
        self._persist_engine_state(  # type: ignore[attr-defined]
            objective_id=objective_id,
            status=AutopilotStatus.PLANNING,
            plan_id=plan.plan_id,
        )

        logger.info(
            "AutopilotEngine: Started objective %s with plan %s (%d steps)",
            objective_id, plan.plan_id, len(plan.steps),
        )
        return plan

    # ── Objective Lifecycle ─────────────────────────────────

    def pause_objective(self, objective_id: str) -> bool:
        """Pause an active objective.

        Args:
            objective_id: The objective ID to pause.

        Returns:
            True if the objective was paused, False if not found or not active.
        """
        with self._lock:  # type: ignore[attr-defined]
            objective = self.objective_store.get_objective(objective_id)  # type: ignore[attr-defined]
            if objective is None or objective.status != ObjectiveStatus.ACTIVE:
                return False

            objective.status = ObjectiveStatus.PAUSED
            self.objective_store.update_objective(objective)  # type: ignore[attr-defined]
            self._objective_statuses[objective_id] = AutopilotStatus.PAUSED  # type: ignore[attr-defined]

            self._persist_engine_state(  # type: ignore[attr-defined]
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
        with self._lock:  # type: ignore[attr-defined]
            objective = self.objective_store.get_objective(objective_id)  # type: ignore[attr-defined]
            if objective is None or objective.status != ObjectiveStatus.PAUSED:
                return False

            objective.status = ObjectiveStatus.ACTIVE
            self.objective_store.update_objective(objective)  # type: ignore[attr-defined]
            self._objective_statuses[objective_id] = AutopilotStatus.IDLE  # type: ignore[attr-defined]

            self._persist_engine_state(  # type: ignore[attr-defined]
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
        with self._lock:  # type: ignore[attr-defined]
            objective = self.objective_store.get_objective(objective_id)  # type: ignore[attr-defined]
            if objective is None:
                return False

            objective.status = ObjectiveStatus.CANCELLED
            self.objective_store.update_objective(objective)  # type: ignore[attr-defined]
            self._objective_statuses[objective_id] = AutopilotStatus.FAILED  # type: ignore[attr-defined]

            self._persist_engine_state(  # type: ignore[attr-defined]
                objective_id=objective_id,
                status=AutopilotStatus.FAILED,
            )

            logger.info("AutopilotEngine: Cancelled objective %s", objective_id)
            return True
