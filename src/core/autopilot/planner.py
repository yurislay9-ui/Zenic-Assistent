"""
ZENIC-AGENTS - Autopilot Planner (Phase D1)

Decomposes objectives into actionable automation steps with dependency
tracking, risk levels, and impact estimation. Uses built-in templates
for common business objectives with a generic fallback.

Thread-safe: All public methods guarded by RLock.
Retry logic: DB operations wrapped with 3 retries, base 0.5s backoff.
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
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  DATACLASSES
# ──────────────────────────────────────────────────────────────

@dataclass
class PlanStep:
    """A single step in an autopilot plan.

    Each step represents one discrete action the system can take,
    with dependencies on other steps and a risk/impact assessment.
    """
    step_id: str = ""
    name: str = ""
    description: str = ""
    action_type: str = ""
    action_config: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    estimated_impact: float = 0.5
    risk_level: str = "low"
    status: str = "planned"

    def __post_init__(self) -> None:
        """Auto-generate step ID if not provided."""
        if not self.step_id:
            self.step_id = f"step-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "step_id": self.step_id,
            "name": self.name,
            "description": self.description,
            "action_type": self.action_type,
            "action_config": self.action_config,
            "depends_on": self.depends_on,
            "estimated_impact": self.estimated_impact,
            "risk_level": self.risk_level,
            "status": self.status,
        }


@dataclass
class PlannedAction:
    """A complete plan for achieving an objective.

    Contains an ordered list of steps with dependency tracking
    and overall plan status.
    """
    plan_id: str = ""
    objective_id: str = ""
    steps: List[PlanStep] = field(default_factory=list)
    created_at: str = ""
    status: str = "draft"
    priority: int = 0

    def __post_init__(self) -> None:
        """Auto-generate plan ID and timestamp if not provided."""
        if not self.plan_id:
            self.plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "plan_id": self.plan_id,
            "objective_id": self.objective_id,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "status": self.status,
            "priority": self.priority,
        }


# ──────────────────────────────────────────────────────────────
#  PLAN TEMPLATES
# ──────────────────────────────────────────────────────────────

_PLAN_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "reduce_overdue_invoices": [
        {
            "name": "monitor_overdue",
            "description": "Monitor overdue invoice rate from billing system",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT COUNT(*) FILTER (WHERE due_date < NOW()) * 100.0 / COUNT(*) FROM invoices",
            },
            "depends_on": [],
            "estimated_impact": 0.2,
            "risk_level": "low",
        },
        {
            "name": "notify_clients",
            "description": "Send payment reminders to clients with overdue invoices",
            "action_type": "email",
            "action_config": {
                "template": "payment_reminder",
                "recipients": "overdue_clients",
            },
            "depends_on": ["monitor_overdue"],
            "estimated_impact": 0.4,
            "risk_level": "low",
        },
        {
            "name": "escalate_morosos",
            "description": "Escalate chronic non-payers to collections process",
            "action_type": "notification",
            "action_config": {
                "channel": "manager_alert",
                "template": "escalation_notice",
            },
            "depends_on": ["notify_clients"],
            "estimated_impact": 0.3,
            "risk_level": "medium",
        },
        {
            "name": "generate_report",
            "description": "Generate overdue invoices reduction report",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT * FROM overdue_report_view",
            },
            "depends_on": ["escalate_morosos"],
            "estimated_impact": 0.1,
            "risk_level": "low",
        },
    ],
    "reduce_no_shows": [
        {
            "name": "monitor_appointments",
            "description": "Monitor appointment no-show rate",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT no_show_rate FROM appointment_stats",
            },
            "depends_on": [],
            "estimated_impact": 0.2,
            "risk_level": "low",
        },
        {
            "name": "send_reminders",
            "description": "Send appointment reminders via email/SMS",
            "action_type": "notification",
            "action_config": {
                "channel": "sms_email",
                "template": "appointment_reminder",
            },
            "depends_on": ["monitor_appointments"],
            "estimated_impact": 0.4,
            "risk_level": "low",
        },
        {
            "name": "optimize_schedule",
            "description": "Optimize scheduling to minimize no-show slots",
            "action_type": "database",
            "action_config": {
                "operation": "update",
                "query": "UPDATE appointment_slots SET optimization = 'no_show_reduction'",
            },
            "depends_on": ["send_reminders"],
            "estimated_impact": 0.25,
            "risk_level": "medium",
        },
        {
            "name": "track_results",
            "description": "Track no-show reduction results over time",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT * FROM no_show_tracking",
            },
            "depends_on": ["optimize_schedule"],
            "estimated_impact": 0.15,
            "risk_level": "low",
        },
    ],
    "reduce_stockouts": [
        {
            "name": "monitor_stock",
            "description": "Monitor stock levels for products near threshold",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT * FROM inventory WHERE quantity < reorder_point",
            },
            "depends_on": [],
            "estimated_impact": 0.2,
            "risk_level": "low",
        },
        {
            "name": "auto_reorder",
            "description": "Automatically place reorders for items below threshold",
            "action_type": "notification",
            "action_config": {
                "channel": "supplier_api",
                "template": "reorder_request",
            },
            "depends_on": ["monitor_stock"],
            "estimated_impact": 0.4,
            "risk_level": "medium",
        },
        {
            "name": "notify_supplier",
            "description": "Notify supplier of pending orders",
            "action_type": "email",
            "action_config": {
                "template": "supplier_order",
                "recipients": "supplier_contacts",
            },
            "depends_on": ["auto_reorder"],
            "estimated_impact": 0.2,
            "risk_level": "low",
        },
        {
            "name": "track_deliveries",
            "description": "Track incoming deliveries and update inventory",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT * FROM purchase_orders WHERE status = 'in_transit'",
            },
            "depends_on": ["notify_supplier"],
            "estimated_impact": 0.2,
            "risk_level": "low",
        },
    ],
    "increase_revenue": [
        {
            "name": "monitor_sales",
            "description": "Monitor current sales metrics and revenue trends",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT * FROM revenue_dashboard",
            },
            "depends_on": [],
            "estimated_impact": 0.15,
            "risk_level": "low",
        },
        {
            "name": "identify_opportunities",
            "description": "Identify upselling and cross-selling opportunities",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT * FROM sales_opportunities WHERE score > 0.7",
            },
            "depends_on": ["monitor_sales"],
            "estimated_impact": 0.3,
            "risk_level": "low",
        },
        {
            "name": "create_campaigns",
            "description": "Create targeted marketing campaigns for identified opportunities",
            "action_type": "email",
            "action_config": {
                "template": "marketing_campaign",
                "recipients": "target_segment",
            },
            "depends_on": ["identify_opportunities"],
            "estimated_impact": 0.35,
            "risk_level": "medium",
        },
        {
            "name": "track_conversions",
            "description": "Track campaign conversions and revenue impact",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT * FROM campaign_performance",
            },
            "depends_on": ["create_campaigns"],
            "estimated_impact": 0.2,
            "risk_level": "low",
        },
    ],
}

_GENERIC_PLAN_TEMPLATE: List[Dict[str, Any]] = [
    {
        "name": "monitor_metric",
        "description": "Monitor the objective metric from data source",
        "action_type": "database",
        "action_config": {
            "operation": "query",
        },
        "depends_on": [],
        "estimated_impact": 0.2,
        "risk_level": "low",
    },
    {
        "name": "notify_on_threshold",
        "description": "Send notification when metric crosses threshold",
        "action_type": "notification",
        "action_config": {
            "channel": "manager_alert",
            "template": "threshold_alert",
        },
        "depends_on": ["monitor_metric"],
        "estimated_impact": 0.3,
        "risk_level": "low",
    },
    {
        "name": "create_task",
        "description": "Create a corrective task based on metric analysis",
        "action_type": "database",
        "action_config": {
            "operation": "insert",
        },
        "depends_on": ["notify_on_threshold"],
        "estimated_impact": 0.3,
        "risk_level": "medium",
    },
    {
        "name": "track_progress",
        "description": "Track progress of corrective actions over time",
        "action_type": "database",
        "action_config": {
            "operation": "query",
        },
        "depends_on": ["create_task"],
        "estimated_impact": 0.2,
        "risk_level": "low",
    },
]


def _match_template(objective: Any) -> List[Dict[str, Any]]:
    """Match an objective to the best plan template.

    Tries to match based on objective name, description, tags, and
    metadata. Falls back to the generic template if no match is found.

    Args:
        objective: An Objective instance.

    Returns:
        A list of step template dictionaries.
    """
    # Build search text from objective fields
    name_lower = getattr(objective, "name", "").lower()
    desc_lower = getattr(objective, "description", "").lower()
    tags = getattr(objective, "tags", [])
    tags_lower = [t.lower() for t in tags]
    metadata = getattr(objective, "metadata", {})
    search_terms = [name_lower, desc_lower] + tags_lower

    # Keyword mapping for template matching
    keyword_map: Dict[str, str] = {
        "reduce_overdue_invoices": ["overdue", "invoice", "factura", "moroso", "vencida"],
        "reduce_no_shows": ["no_show", "no show", "ausencia", "cita", "appointment"],
        "reduce_stockouts": ["stockout", "stock", "inventario", "inventory", "agotado"],
        "increase_revenue": ["revenue", "ingreso", "sales", "venta", "revenue"],
    }

    best_match: Optional[str] = None
    best_score = 0

    for template_key, keywords in keyword_map.items():
        score = sum(1 for term in search_terms for kw in keywords if kw in term)
        if score > best_score:
            best_score = score
            best_match = template_key

    if best_match and best_score > 0:
        logger.info(
            "AutopilotPlanner: Matched template '%s' (score=%d) for objective",
            best_match, best_score,
        )
        return _PLAN_TEMPLATES[best_match]

    return _GENERIC_PLAN_TEMPLATE


# ──────────────────────────────────────────────────────────────
#  RETRY HELPER
# ──────────────────────────────────────────────────────────────

def _retry_db_operation(
    func: Any,
    max_retries: int = 3,
    base_delay: float = 0.5,
) -> Any:
    """Execute a function with retry logic for DB operations.

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
                "AutopilotPlanner: DB retry %d/%d after %.2fs — %s",
                attempt + 1, max_retries, delay, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
        except Exception as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "AutopilotPlanner: Unexpected error on retry %d/%d — %s",
                attempt + 1, max_retries, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


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
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS _zenic_autopilot_plans (
                            plan_id TEXT PRIMARY KEY,
                            objective_id TEXT NOT NULL,
                            steps TEXT NOT NULL DEFAULT '[]',
                            created_at TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL DEFAULT 'draft',
                            priority INTEGER NOT NULL DEFAULT 0
                        )
                    """)
                    conn.execute("""
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
                    conn.execute(
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
                    row = conn.execute(
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
                        rows = conn.execute(
                            """SELECT * FROM _zenic_autopilot_plans
                               WHERE objective_id = ?
                               ORDER BY created_at DESC""",
                            (objective_id,),
                        ).fetchall()
                    else:
                        rows = conn.execute(
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
                    conn.execute(
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
        if not plan.steps:
            return 0.0

        # Count how many steps depend on each step
        dependency_count: Dict[str, int] = {}
        for step in plan.steps:
            for dep_id in step.depends_on:
                dependency_count[dep_id] = dependency_count.get(dep_id, 0) + 1

        total_impact = 0.0
        for step in plan.steps:
            # Steps that unblock others get a multiplier
            weight = 1.0 + (0.5 * dependency_count.get(step.step_id, 0))
            total_impact += step.estimated_impact * weight

        # Normalize to [0, 1]
        max_possible = sum(
            s.estimated_impact * (1.0 + 0.5 * dependency_count.get(s.step_id, 0))
            for s in plan.steps
        )
        if max_possible <= 0:
            return 0.0

        # Return the raw weighted sum capped at 1.0
        return min(1.0, round(total_impact / max_possible, 4))

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


__all__ = [
    "PlanStep",
    "PlannedAction",
    "AutopilotPlanner",
    "get_autopilot_planner",
    "reset_autopilot_planner",
]
