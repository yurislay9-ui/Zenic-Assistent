"""ZENIC-AGENTS - Autopilot Engine: Execution Mixin

Provides the main execution cycle and step execution methods
for the AutopilotEngine class.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Any, Dict, List, Optional

from ._status import AutopilotStatus

from src.core.autopilot.objective import Objective, ObjectiveStatus
from src.core.autopilot.planner import PlanStep
from src.core.autopilot.feedback import FeedbackAction

logger = logging.getLogger(__name__)


class _ExecutionMixin:
    """Mixin providing the main execution cycle for AutopilotEngine."""

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
        self._ensure_schema()  # type: ignore[attr-defined]
        with self._lock:  # type: ignore[attr-defined]
            self._cycle_count += 1  # type: ignore[attr-defined]
            self._stats["cycles_executed"] += 1  # type: ignore[attr-defined]

            # 1. Get objective and plan
            objective = self.objective_store.get_objective(objective_id)  # type: ignore[attr-defined]
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

            plan = self._active_plans.get(objective_id)  # type: ignore[attr-defined]
            if plan is None:
                plans = self.planner.list_plans(objective_id=objective_id)  # type: ignore[attr-defined]
                if plans:
                    plan = plans[0]
                    self._active_plans[objective_id] = plan  # type: ignore[attr-defined]
                else:
                    plan = self.start_objective(objective_id)  # type: ignore[attr-defined]

            self._objective_statuses[objective_id] = AutopilotStatus.EXECUTING  # type: ignore[attr-defined]

            # 2. Measure KPIs
            measurements = self.kpi_tracker.measure_all_for_objective(objective)  # type: ignore[attr-defined]
            kpi_summary = {m.metric_name: m.value for m in measurements}

            # 3. Evaluate feedback
            feedback_cycle = self.feedback.evaluate_cycle(  # type: ignore[attr-defined]
                objective=objective,
                plan=plan,
                kpi_tracker=self.kpi_tracker,  # type: ignore[attr-defined]
            )

            # 4. Check autonomy level
            autonomy_config = self.autonomy_manager.get_config(  # type: ignore[attr-defined]
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
                    impact = self.impact_preview_engine.preview_action(  # type: ignore[attr-defined]
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
                    safety_result = self.safety_gate.check(  # type: ignore[attr-defined]
                        action_type=step.action_type,
                        config=step.action_config,
                    )
                    safety_verdict = getattr(safety_result, "verdict", None)
                    if safety_verdict is not None and str(safety_verdict) == "DENY":
                        self.planner.update_step_status(  # type: ignore[attr-defined]
                            plan.plan_id, step.step_id, "blocked",
                        )
                        skipped_actions.append({
                            "step_id": step.step_id,
                            "name": step.name,
                            "reason": "Safety gate denied",
                        })
                        self._stats["actions_skipped"] += 1  # type: ignore[attr-defined]
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
                        self.planner.update_step_status(  # type: ignore[attr-defined]
                            plan.plan_id, step.step_id, "completed",
                        )
                        self._stats["actions_executed"] += 1  # type: ignore[attr-defined]
                    except Exception as exc:
                        logger.error(
                            "AutopilotEngine: Step %s execution failed: %s",
                            step.step_id, exc,
                        )
                        self.planner.update_step_status(  # type: ignore[attr-defined]
                            plan.plan_id, step.step_id, "failed",
                        )
                        executed_actions.append({
                            "step_id": step.step_id,
                            "name": step.name,
                            "error": str(exc),
                        })
                        if autonomy_config.pause_on_exception:
                            self._objective_statuses[objective_id] = AutopilotStatus.PAUSED  # type: ignore[attr-defined]
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
                    self._stats["actions_approved"] += 1  # type: ignore[attr-defined]

                    # Check max actions per cycle
                    if len(executed_actions) >= autonomy_config.max_actions_per_cycle:
                        break

            # Handle feedback-driven actions
            if feedback_cycle.action_taken == FeedbackAction.PAUSE_OBJECTIVE:
                self.pause_objective(objective_id)  # type: ignore[attr-defined]
                self._objective_statuses[objective_id] = AutopilotStatus.PAUSED  # type: ignore[attr-defined]
            elif feedback_cycle.action_taken == FeedbackAction.ESCALATE_TO_HUMAN:
                self._stats["escalations"] += 1  # type: ignore[attr-defined]
                logger.warning(
                    "AutopilotEngine: Objective %s escalated to human",
                    objective_id,
                )

            # Check if objective is completed
            all_targets_met = all(t.is_met() for t in objective.targets)
            if all_targets_met:
                objective.status = ObjectiveStatus.COMPLETED
                self.objective_store.update_objective(objective)  # type: ignore[attr-defined]
                self._objective_statuses[objective_id] = AutopilotStatus.COMPLETED  # type: ignore[attr-defined]
                self._stats["objectives_completed"] += 1  # type: ignore[attr-defined]

            # Update engine status
            if approval_needed and self._objective_statuses.get(objective_id) != AutopilotStatus.PAUSED:  # type: ignore[attr-defined]
                self._objective_statuses[objective_id] = AutopilotStatus.WAITING_APPROVAL  # type: ignore[attr-defined]

            # Persist engine state
            cycle_result = {
                "cycle_number": self._cycle_count,  # type: ignore[attr-defined]
                "kpi_summary": kpi_summary,
                "feedback_action": feedback_cycle.action_taken.value,
                "feedback_analysis": feedback_cycle.analysis,
                "executed_actions": executed_actions,
                "pending_approvals": pending_approvals,
                "skipped_actions": skipped_actions,
                "all_targets_met": all_targets_met,
            }

            self._persist_engine_state(  # type: ignore[attr-defined]
                objective_id=objective_id,
                status=self._objective_statuses.get(objective_id, AutopilotStatus.IDLE),  # type: ignore[attr-defined]
                plan_id=plan.plan_id,
                result=cycle_result,
            )

            return {
                "objective_id": objective_id,
                "status": self._objective_statuses.get(objective_id, AutopilotStatus.IDLE).value,  # type: ignore[attr-defined]
                **cycle_result,
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
            try:
                loop = asyncio.get_running_loop()
                # We're inside an existing event loop, schedule accordingly
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.action_dispatcher.dispatch(request),  # type: ignore[attr-defined]
                    )
                    result = future.result(timeout=30)
            except RuntimeError:
                # No running loop, safe to use asyncio.run
                result = asyncio.run(self.action_dispatcher.dispatch(request))  # type: ignore[attr-defined]

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
