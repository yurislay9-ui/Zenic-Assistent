"""
ZENIC-AGENTS - Autopilot Planner Core

The main AutopilotPlanner class that decomposes objectives into
actionable automation steps with dependency tracking, risk levels,
and impact estimation. Plans are persisted to SQLite.

Thread-safe: All public methods guarded by RLock.
Retry logic: DB operations wrapped with 3 retries, base 0.5s backoff.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from src.core.autopilot.planner._optimizer import _retry_db_operation, estimate_plan_impact
from src.core.autopilot.planner._scheduler import _match_template
from src.core.autopilot.planner._types import PlanStep, PlannedAction

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  AUTOPILOT PLANNER
# ──────────────────────────────────────────────────────────────

class AutopilotPlanner:
    """Decomposes objectives into actionable automation steps.

    Uses built-in templates for common business objectives (overdue
    invoices, no-shows, stockouts, revenue) with a generic fallback
    for unknown objectives. Plans are persisted to SQLite.

    Thread-safe: All public methods guarded by RLock.
    """

    def __init__(self, db_path: str = "autopilot_planner.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._initialized = False

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
                    conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                        CREATE TABLE IF NOT EXISTS _zenic_autopilot_plans (
                            plan_id TEXT PRIMARY KEY,
                            objective_id TEXT NOT NULL,
                            steps TEXT NOT NULL DEFAULT '[]',
                            created_at TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL DEFAULT 'draft',
                            priority INTEGER NOT NULL DEFAULT 0
                        )
                    """)
                    conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                        CREATE INDEX IF NOT EXISTS idx_zenic_plan_obj
                        ON _zenic_autopilot_plans(objective_id)
                    """)
                    conn.commit()
                finally:
                    conn.close()

            _retry_db_operation(_init)
            self._initialized = True
            logger.info("AutopilotPlanner: Schema initialized at %s", self._db_path)

    # ── Core Planning ───────────────────────────────────────

    def plan_for_objective(self, objective: Any) -> PlannedAction:
        """Decompose an objective into an actionable plan.

        Matches the objective to a built-in template based on name,
        description, and tags. Falls back to a generic plan template
        if no match is found.

        Args:
            objective: An Objective instance with targets and metadata.

        Returns:
            A PlannedAction with ordered, dependency-tracked steps.
        """
        template_steps = _match_template(objective)

        # Resolve step IDs for dependency linking
        step_id_map: Dict[str, str] = {}
        steps: List[PlanStep] = []

        for tmpl in template_steps:
            step = PlanStep(
                name=tmpl["name"],
                description=tmpl["description"],
                action_type=tmpl["action_type"],
                action_config=dict(tmpl.get("action_config", {})),
                depends_on=[],  # Will be resolved below
                estimated_impact=tmpl.get("estimated_impact", 0.5),
                risk_level=tmpl.get("risk_level", "low"),
                status="planned",
            )
            step_id_map[tmpl["name"]] = step.step_id
            steps.append(step)

        # Resolve dependency names to step IDs
        for i, tmpl in enumerate(template_steps):
            dep_names = tmpl.get("depends_on", [])
            resolved = [
                step_id_map[name]
                for name in dep_names
                if name in step_id_map
            ]
            steps[i].depends_on = resolved

        # Determine priority from objective
        priority_val = 0
        obj_priority = getattr(objective, "priority", None)
        if obj_priority is not None:
            priority_map = {"low": 1, "normal": 2, "high": 3, "critical": 4}
            priority_key = obj_priority.value if hasattr(obj_priority, "value") else str(obj_priority)
            priority_val = priority_map.get(priority_key, 2)

        plan = PlannedAction(
            objective_id=getattr(objective, "objective_id", ""),
            steps=steps,
            status="draft",
            priority=priority_val,
        )

        # Persist the plan
        self._ensure_schema()
        with self._lock:
            data = plan.to_dict()

            def _insert() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """INSERT INTO _zenic_autopilot_plans
                           (plan_id, objective_id, steps, created_at, status, priority)
                           VALUES (?,?,?,?,?,?)""",
                        (
                            data["plan_id"],
                            data["objective_id"],
                            json.dumps(data["steps"]),
                            data["created_at"],
                            data["status"],
                            data["priority"],
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

            _retry_db_operation(_insert)

        logger.info(
            "AutopilotPlanner: Created plan %s with %d steps for objective %s",
            plan.plan_id, len(steps), plan.objective_id,
        )
        return plan

    def get_plan(self, plan_id: str) -> Optional[PlannedAction]:
        """Get a plan by ID.

        Args:
            plan_id: The unique identifier of the plan.

        Returns:
            The PlannedAction if found, or None.
        """
        self._ensure_schema()
        with self._lock:

            def _fetch() -> Optional[PlannedAction]:
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                try:
                    row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT * FROM _zenic_autopilot_plans WHERE plan_id = ?",
                        (plan_id,),
                    ).fetchone()
                    if row is None:
                        return None
                    return self._row_to_plan(row)
                finally:
                    conn.close()

            return _retry_db_operation(_fetch)

    def list_plans(self, objective_id: str = "") -> List[PlannedAction]:
        """List plans, optionally filtered by objective.

        Args:
            objective_id: Optional objective ID filter.

        Returns:
            A list of matching PlannedActions.
        """
        self._ensure_schema()
        with self._lock:

            def _list() -> List[PlannedAction]:
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                try:
                    if objective_id:
                        rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                            """SELECT * FROM _zenic_autopilot_plans
                               WHERE objective_id = ?
                               ORDER BY created_at DESC""",
                            (objective_id,),
                        ).fetchall()
                    else:
                        rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                            """SELECT * FROM _zenic_autopilot_plans
                               ORDER BY created_at DESC""",
                        ).fetchall()
                    return [self._row_to_plan(r) for r in rows]
                finally:
                    conn.close()

            return _retry_db_operation(_list)

    def update_step_status(
        self, plan_id: str, step_id: str, status: str,
    ) -> bool:
        """Update the status of a specific step within a plan.

        Args:
            plan_id: The plan ID.
            step_id: The step ID within the plan.
            status: New status (e.g. "planned", "executing", "completed", "failed").

        Returns:
            True if the step was found and updated, False otherwise.
        """
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

            # Persist the updated plan
            data = plan.to_dict()

            def _update() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """UPDATE _zenic_autopilot_plans
                           SET steps = ?, status = ?
                           WHERE plan_id = ?""",
                        (json.dumps(data["steps"]), data["status"], plan_id),
                    )
                    conn.commit()
                finally:
                    conn.close()

            _retry_db_operation(_update)
            logger.info(
                "AutopilotPlanner: Updated step %s in plan %s to '%s'",
                step_id, plan_id, status,
            )
            return True

    def estimate_plan_impact(self, plan: PlannedAction) -> float:
        """Estimate the total impact of a plan.

        Sums the estimated_impact of all steps, weighted by dependencies.
        Steps that are depended upon by other steps get a 1.5x multiplier
        since they unblock further actions.

        Args:
            plan: The PlannedAction to evaluate.

        Returns:
            A float between 0.0 and 1.0 representing estimated total impact.
        """
        return estimate_plan_impact(plan)

    # ── Row Converter ──────────────────────────────────────

    @staticmethod
    def _row_to_plan(row: sqlite3.Row) -> PlannedAction:
        """Convert a database row to a PlannedAction instance."""
        steps_data = json.loads(row["steps"])
        steps = [PlanStep(**s) for s in steps_data]
        return PlannedAction(
            plan_id=row["plan_id"],
            objective_id=row["objective_id"],
            steps=steps,
            created_at=row["created_at"],
            status=row["status"],
            priority=row["priority"],
        )


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

_autopilot_planner_instance: Optional[AutopilotPlanner] = None
_autopilot_planner_lock = threading.Lock()


def get_autopilot_planner(db_path: str = "autopilot_planner.sqlite") -> AutopilotPlanner:
    """Get or create the global AutopilotPlanner instance.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        The singleton AutopilotPlanner instance.
    """
    global _autopilot_planner_instance
    with _autopilot_planner_lock:
        if _autopilot_planner_instance is None:
            _autopilot_planner_instance = AutopilotPlanner(db_path=db_path)
        return _autopilot_planner_instance


def reset_autopilot_planner() -> None:
    """Reset the global AutopilotPlanner instance (for testing)."""
    global _autopilot_planner_instance
    with _autopilot_planner_lock:
        _autopilot_planner_instance = None
