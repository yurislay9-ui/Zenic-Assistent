"""
autopilot.planner._mixin_core — Core planning and persistence mixin.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from src.core.autopilot.planner._types import PlanStep, PlannedAction
from src.core.autopilot.planner._templates import match_template
from src.core.autopilot.planner._helpers import retry_db_operation

logger = logging.getLogger(__name__)


class CoreMixin:
    """Mixin providing core planning and persistence methods."""

    # Provided by main class
    _db_path: str
    _lock: object
    _initialized: bool

    def _ensure_schema(self) -> None:
        """Create the plans table if it does not exist."""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return

            def _init() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute("""  # nosemgrep
                        CREATE TABLE IF NOT EXISTS _zenic_autopilot_plans (
                            plan_id TEXT PRIMARY KEY,
                            objective_id TEXT NOT NULL,
                            steps TEXT NOT NULL DEFAULT '[]',
                            created_at TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL DEFAULT 'draft',
                            priority INTEGER NOT NULL DEFAULT 0
                        )
                    """)
                    conn.execute("""  # nosemgrep
                        CREATE INDEX IF NOT EXISTS idx_zenic_plan_obj
                        ON _zenic_autopilot_plans(objective_id)
                    """)
                    conn.commit()
                finally:
                    conn.close()

            retry_db_operation(_init)
            self._initialized = True

    # ── Core Planning ───────────────────────────────────────

    def plan_for_objective(self, objective: Any) -> PlannedAction:
        """Decompose an objective into an actionable plan."""
        template_steps = match_template(objective)

        step_id_map: Dict[str, str] = {}
        steps: List[PlanStep] = []

        for tmpl in template_steps:
            step = PlanStep(
                name=tmpl["name"],
                description=tmpl["description"],
                action_type=tmpl["action_type"],
                action_config=dict(tmpl.get("action_config", {})),
                depends_on=[],
                estimated_impact=tmpl.get("estimated_impact", 0.5),
                risk_level=tmpl.get("risk_level", "low"),
                status="planned",
            )
            step_id_map[tmpl["name"]] = step.step_id
            steps.append(step)

        for i, tmpl in enumerate(template_steps):
            dep_names = tmpl.get("depends_on", [])
            resolved = [step_id_map[name] for name in dep_names if name in step_id_map]
            steps[i].depends_on = resolved

        priority_val = 0
        obj_priority = getattr(objective, "priority", None)
        if obj_priority is not None:
            priority_map = {"low": 1, "normal": 2, "high": 3, "critical": 4}
            priority_key = obj_priority.value if hasattr(obj_priority, "value") else str(obj_priority)
            priority_val = priority_map.get(priority_key, 2)

        plan = PlannedAction(
            objective_id=getattr(objective, "objective_id", ""),
            steps=steps, status="draft", priority=priority_val,
        )

        # Persist the plan
        self._ensure_schema()
        with self._lock:
            data = plan.to_dict()

            def _insert() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(  # nosemgrep
                        "INSERT INTO _zenic_autopilot_plans "
                        "(plan_id, objective_id, steps, created_at, status, priority) "
                        "VALUES (?,?,?,?,?,?)",
                        (data["plan_id"], data["objective_id"],
                         json.dumps(data["steps"]), data["created_at"],
                         data["status"], data["priority"]),
                    )
                    conn.commit()
                finally:
                    conn.close()

            retry_db_operation(_insert)

        logger.info(
            "AutopilotPlanner: Created plan %s with %d steps for objective %s",
            plan.plan_id, len(steps), plan.objective_id,
        )
        return plan

    def get_plan(self, plan_id: str) -> Optional[PlannedAction]:
        """Get a plan by ID."""
        self._ensure_schema()
        with self._lock:

            def _fetch() -> Optional[PlannedAction]:
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                try:
                    row = conn.execute(  # nosemgrep
                        "SELECT * FROM _zenic_autopilot_plans WHERE plan_id = ?",
                        (plan_id,),
                    ).fetchone()
                    if row is None:
                        return None
                    return self._row_to_plan(row)
                finally:
                    conn.close()

            return retry_db_operation(_fetch)

    def list_plans(self, objective_id: str = "") -> List[PlannedAction]:
        """List plans, optionally filtered by objective."""
        self._ensure_schema()
        with self._lock:

            def _list() -> List[PlannedAction]:
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                try:
                    if objective_id:
                        rows = conn.execute(  # nosemgrep
                            "SELECT * FROM _zenic_autopilot_plans WHERE objective_id = ? ORDER BY created_at DESC",
                            (objective_id,),
                        ).fetchall()
                    else:
                        rows = conn.execute(  # nosemgrep
                            "SELECT * FROM _zenic_autopilot_plans ORDER BY created_at DESC",
                        ).fetchall()
                    return [self._row_to_plan(r) for r in rows]
                finally:
                    conn.close()

            return retry_db_operation(_list)

    def update_step_status(self, plan_id: str, step_id: str, status: str) -> bool:
        """Update the status of a specific step within a plan."""
        self._ensure_schema()
        with self._lock:
            plan = self.get_plan(plan_id)
            if plan is None:
                return False

            found = False
            for step in plan.steps:
                if step.step_id == step_id:
                    step.status = status
                    found = True
                    break

            if not found:
                return False

            data = plan.to_dict()

            def _update() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(  # nosemgrep
                        "UPDATE _zenic_autopilot_plans SET steps = ?, status = ? WHERE plan_id = ?",
                        (json.dumps(data["steps"]), data["status"], plan_id),
                    )
                    conn.commit()
                finally:
                    conn.close()

            retry_db_operation(_update)
            logger.info("AutopilotPlanner: Updated step %s in plan %s to '%s'", step_id, plan_id, status)
            return True

    def estimate_plan_impact(self, plan: PlannedAction) -> float:
        """Estimate the total impact of a plan."""
        if not plan.steps:
            return 0.0

        dependency_count: Dict[str, int] = {}
        for step in plan.steps:
            for dep_id in step.depends_on:
                dependency_count[dep_id] = dependency_count.get(dep_id, 0) + 1

        total_impact = 0.0
        for step in plan.steps:
            weight = 1.0 + (0.5 * dependency_count.get(step.step_id, 0))
            total_impact += step.estimated_impact * weight

        max_possible = sum(
            s.estimated_impact * (1.0 + 0.5 * dependency_count.get(s.step_id, 0))
            for s in plan.steps
        )
        if max_possible <= 0:
            return 0.0

        return min(1.0, round(total_impact / max_possible, 4))

    # ── Row Converter ──────────────────────────────────────

    @staticmethod
    def _row_to_plan(row: sqlite3.Row) -> PlannedAction:
        """Convert a database row to a PlannedAction instance."""
        steps_data = json.loads(row["steps"])
        steps = [PlanStep(**s) for s in steps_data]
        return PlannedAction(
            plan_id=row["plan_id"], objective_id=row["objective_id"],
            steps=steps, created_at=row["created_at"],
            status=row["status"], priority=row["priority"],
        )
