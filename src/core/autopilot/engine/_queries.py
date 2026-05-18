"""ZENIC-AGENTS - Autopilot Engine: Queries Mixin

Provides status query and statistics methods for the AutopilotEngine class.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from ._status import AutopilotStatus

logger = logging.getLogger(__name__)


class _QueriesMixin:
    """Mixin providing status query methods for AutopilotEngine."""

    # ── Status Queries ──────────────────────────────────────

    def get_status(self, objective_id: str) -> Dict[str, Any]:
        """Get comprehensive status for an objective.

        Args:
            objective_id: The objective ID to query.

        Returns:
            Dictionary with objective status, KPI progress, plan, and feedback.
        """
        objective = self.objective_store.get_objective(objective_id)  # type: ignore[attr-defined]
        if objective is None:
            return {"objective_id": objective_id, "status": "not_found"}

        engine_status = self._objective_statuses.get(  # type: ignore[attr-defined]
            objective_id, AutopilotStatus.IDLE,
        )
        progress = self.kpi_tracker.get_objective_progress(objective_id)  # type: ignore[attr-defined]
        plan = self._active_plans.get(objective_id)  # type: ignore[attr-defined]
        latest_feedback = self.feedback.get_latest_cycle(objective_id)  # type: ignore[attr-defined]

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
        objectives = self.objective_store.list_objectives()  # type: ignore[attr-defined]
        return [self.get_status(o.objective_id) for o in objectives]

    def check_and_execute(self) -> List[Dict[str, Any]]:
        """Run one cycle for all active objectives.

        Iterates over all active objectives and executes a cycle
        for each one. Returns a summary of all cycle results.

        Returns:
            A list of cycle result dictionaries.
        """
        active = self.objective_store.get_active_objectives()  # type: ignore[attr-defined]
        results: List[Dict[str, Any]] = []

        for objective in active:
            try:
                result = self.execute_cycle(objective.objective_id)  # type: ignore[attr-defined]
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
            **self._stats,  # type: ignore[attr-defined]
            "cycle_count": self._cycle_count,  # type: ignore[attr-defined]
            "active_objectives": sum(
                1 for s in self._objective_statuses.values()  # type: ignore[attr-defined]
                if s in (AutopilotStatus.EXECUTING, AutopilotStatus.PLANNING, AutopilotStatus.WAITING_APPROVAL)
            ),
            "paused_objectives": sum(
                1 for s in self._objective_statuses.values()  # type: ignore[attr-defined]
                if s == AutopilotStatus.PAUSED
            ),
        }
