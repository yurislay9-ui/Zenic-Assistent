"""
ZENIC-AGENTS - Closed-Loop Feedback (Phase D1)

Measures the result of autopilot actions and adjusts strategy based on
KPI feedback. Implements the control loop: measure → evaluate → adjust.

Decision logic:
  - Improvement > 0  → CONTINUE
  - Improvement == 0 for max_cycles → ADJUST_STRATEGY
  - Improvement < 0  → CHANGE_APPROACH
  - Negative for 3+ consecutive cycles → ESCALATE_TO_HUMAN
  - Significant worsening → PAUSE_OBJECTIVE

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
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  ENUMS
# ──────────────────────────────────────────────────────────────

class FeedbackAction(str, Enum):
    """Action to take based on feedback evaluation."""
    CONTINUE = "continue"
    ADJUST_STRATEGY = "adjust_strategy"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    PAUSE_OBJECTIVE = "pause_objective"
    CHANGE_APPROACH = "change_approach"


# ──────────────────────────────────────────────────────────────
#  DATACLASSES
# ──────────────────────────────────────────────────────────────

@dataclass
class FeedbackCycle:
    """A single evaluation cycle in the closed-loop feedback system.

    Records KPI values before and after an autopilot cycle, along with
    the determined action and analysis.
    """
    cycle_id: str = ""
    objective_id: str = ""
    plan_id: str = ""
    cycle_number: int = 0
    kpi_before: Dict[str, float] = field(default_factory=dict)
    kpi_after: Dict[str, float] = field(default_factory=dict)
    action_taken: FeedbackAction = FeedbackAction.CONTINUE
    analysis: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        """Auto-generate ID and timestamp if not provided."""
        if not self.cycle_id:
            self.cycle_id = f"fb-{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def improvement(self) -> float:
        """Calculate average improvement across all KPIs.

        For each metric, improvement is calculated as the movement
        toward the target from before to after. Positive values
        indicate improvement.

        Returns:
            Average improvement across all KPIs.
        """
        if not self.kpi_before or not self.kpi_after:
            return 0.0

        improvements: List[float] = []
        for metric, after_val in self.kpi_after.items():
            before_val = self.kpi_before.get(metric, after_val)
            # Positive delta means value increased
            delta = after_val - before_val
            improvements.append(delta)

        if not improvements:
            return 0.0
        return round(sum(improvements) / len(improvements), 6)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "cycle_id": self.cycle_id,
            "objective_id": self.objective_id,
            "plan_id": self.plan_id,
            "cycle_number": self.cycle_number,
            "kpi_before": self.kpi_before,
            "kpi_after": self.kpi_after,
            "action_taken": self.action_taken.value,
            "analysis": self.analysis,
            "timestamp": self.timestamp,
        }


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
                "ClosedLoopFeedback: DB retry %d/%d after %.2fs — %s",
                attempt + 1, max_retries, delay, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
        except Exception as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "ClosedLoopFeedback: Unexpected error on retry %d/%d — %s",
                attempt + 1, max_retries, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────
#  CLOSED-LOOP FEEDBACK
# ──────────────────────────────────────────────────────────────

class ClosedLoopFeedback:
    """Measures results and adjusts strategy for autopilot objectives.

    Evaluates each autopilot cycle by comparing KPIs before and after,
    then determines the appropriate action (continue, adjust, escalate,
    pause, or change approach).

    Thread-safe: All public methods guarded by RLock.
    """

    def __init__(
        self,
        db_path: str = "autopilot_feedback.sqlite",
        max_cycles_without_improvement: int = 3,
    ) -> None:
        self._db_path = db_path
        self._max_cycles_without_improvement = max_cycles_without_improvement
        self._lock = threading.RLock()
        self._initialized = False

    def _ensure_schema(self) -> None:
        """Create the feedback cycles table if it does not exist."""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return

            def _init() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                        CREATE TABLE IF NOT EXISTS _zenic_feedback_cycles (
                            cycle_id TEXT PRIMARY KEY,
                            objective_id TEXT NOT NULL,
                            plan_id TEXT NOT NULL DEFAULT '',
                            cycle_number INTEGER NOT NULL DEFAULT 0,
                            kpi_before TEXT NOT NULL DEFAULT '{}',
                            kpi_after TEXT NOT NULL DEFAULT '{}',
                            action_taken TEXT NOT NULL DEFAULT 'continue',
                            analysis TEXT NOT NULL DEFAULT '',
                            timestamp TEXT NOT NULL DEFAULT ''
                        )
                    """)
                    conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                        CREATE INDEX IF NOT EXISTS idx_zenic_fb_obj
                        ON _zenic_feedback_cycles(objective_id)
                    """)
                    conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                        CREATE INDEX IF NOT EXISTS idx_zenic_fb_obj_ts
                        ON _zenic_feedback_cycles(objective_id, timestamp)
                    """)
                    conn.commit()
                finally:
                    conn.close()

            _retry_db_operation(_init)
            self._initialized = True
            logger.info("ClosedLoopFeedback: Schema initialized at %s", self._db_path)

    # ── Core Evaluation ─────────────────────────────────────

    def evaluate_cycle(
        self,
        objective: Any,
        plan: Any,
        kpi_tracker: Any,
    ) -> FeedbackCycle:
        """Evaluate an autopilot cycle and determine the next action.

        Gets latest KPI measurements, compares with the previous cycle,
        and determines the appropriate action based on improvement trends.

        Args:
            objective: An Objective instance.
            plan: A PlannedAction instance.
            kpi_tracker: A KPITracker instance for querying measurements.

        Returns:
            A FeedbackCycle with the evaluation result and determined action.
        """
        self._ensure_schema()

        # Get KPI measurements before this cycle
        previous_cycles = self.get_cycles(objective.objective_id, limit=1)
        cycle_number = 1
        kpi_before: Dict[str, float] = {}

        if previous_cycles:
            last_cycle = previous_cycles[0]
            cycle_number = last_cycle.cycle_number + 1
            kpi_before = dict(last_cycle.kpi_after)

        # Measure current KPIs
        measurements = kpi_tracker.measure_all_for_objective(objective)
        kpi_after: Dict[str, float] = {}
        for m in measurements:
            kpi_after[m.metric_name] = m.value

        # If no previous measurements, use target current values as before
        if not kpi_before:
            targets = getattr(objective, "targets", [])
            for t in targets:
                if t.metric_name not in kpi_before:
                    kpi_before[t.metric_name] = t.current_value

        # Determine action based on improvement
        action, analysis = self._determine_action(
            objective_id=objective.objective_id,
            kpi_before=kpi_before,
            kpi_after=kpi_after,
            cycle_number=cycle_number,
            targets=getattr(objective, "targets", []),
        )

        cycle = FeedbackCycle(
            objective_id=objective.objective_id,
            plan_id=getattr(plan, "plan_id", ""),
            cycle_number=cycle_number,
            kpi_before=kpi_before,
            kpi_after=kpi_after,
            action_taken=action,
            analysis=analysis,
        )

        # Persist the cycle
        with self._lock:
            data = cycle.to_dict()

            def _insert() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """INSERT INTO _zenic_feedback_cycles
                           (cycle_id, objective_id, plan_id, cycle_number,
                            kpi_before, kpi_after, action_taken, analysis, timestamp)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (
                            data["cycle_id"],
                            data["objective_id"],
                            data["plan_id"],
                            data["cycle_number"],
                            json.dumps(data["kpi_before"]),
                            json.dumps(data["kpi_after"]),
                            data["action_taken"],
                            data["analysis"],
                            data["timestamp"],
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

            _retry_db_operation(_insert)

        logger.info(
            "ClosedLoopFeedback: Cycle %d for %s → %s (%s)",
            cycle_number, objective.objective_id, action.value, analysis,
        )
        return cycle

    def get_cycles(
        self, objective_id: str, limit: int = 20,
    ) -> List[FeedbackCycle]:
        """Get feedback cycles for an objective.

        Args:
            objective_id: The objective ID to query.
            limit: Maximum number of cycles to return.

        Returns:
            A list of FeedbackCycles, newest first.
        """
        self._ensure_schema()
        with self._lock:

            def _fetch() -> List[FeedbackCycle]:
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                try:
                    rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """SELECT * FROM _zenic_feedback_cycles
                           WHERE objective_id = ?
                           ORDER BY cycle_number DESC LIMIT ?""",
                        (objective_id, limit),
                    ).fetchall()
                    return [self._row_to_cycle(r) for r in rows]
                finally:
                    conn.close()

            return _retry_db_operation(_fetch)

    def get_latest_cycle(
        self, objective_id: str,
    ) -> Optional[FeedbackCycle]:
        """Get the latest feedback cycle for an objective.

        Args:
            objective_id: The objective ID to query.

        Returns:
            The latest FeedbackCycle, or None if no cycles exist.
        """
        cycles = self.get_cycles(objective_id, limit=1)
        return cycles[0] if cycles else None

    def should_escalate(self, objective_id: str) -> bool:
        """Check if an objective should be escalated to a human.

        Returns True if the last 3+ consecutive cycles show negative
        improvement, or if the latest action is ESCALATE_TO_HUMAN.

        Args:
            objective_id: The objective ID to check.

        Returns:
            True if escalation is recommended.
        """
        recent = self.get_cycles(objective_id, limit=self._max_cycles_without_improvement + 1)
        if not recent:
            return False

        # Check if latest action already escalated
        if recent[0].action_taken == FeedbackAction.ESCALATE_TO_HUMAN:
            return True

        # Check for consecutive negative cycles
        if len(recent) >= 3:
            consecutive_negative = 0
            for cycle in recent:
                if cycle.improvement() < 0:
                    consecutive_negative += 1
                else:
                    break
            if consecutive_negative >= 3:
                return True

        return False

    # ── Internal Helpers ────────────────────────────────────

    def _determine_action(
        self,
        objective_id: str,
        kpi_before: Dict[str, float],
        kpi_after: Dict[str, float],
        cycle_number: int,
        targets: List[Any],
    ) -> tuple:
        """Determine the feedback action based on KPI changes.

        Returns:
            A tuple of (FeedbackAction, analysis_string).
        """
        # Calculate per-metric improvement relative to targets
        improvements: Dict[str, float] = {}
        for metric, after_val in kpi_after.items():
            before_val = kpi_before.get(metric, after_val)
            # Find the target for this metric to determine direction
            target_val = None
            target_op = "<"
            for t in targets:
                if getattr(t, "metric_name", "") == metric:
                    target_val = getattr(t, "target_value", None)
                    target_op = getattr(t, "operator", "<")
                    break

            delta = after_val - before_val
            if target_val is not None:
                # Determine if delta is improvement relative to target
                if target_op in ("<", "<="):
                    # We want the value to go down
                    improvements[metric] = -delta  # Negative delta = improvement
                elif target_op in (">", ">="):
                    # We want the value to go up
                    improvements[metric] = delta  # Positive delta = improvement
                else:
                    improvements[metric] = -abs(delta)  # Moving away = bad
            else:
                improvements[metric] = delta

        avg_improvement = (
            sum(improvements.values()) / len(improvements)
            if improvements else 0.0
        )

        # Check for significant worsening (> 20% regression)
        significant_worsening = False
        for metric, imp in improvements.items():
            before_val = kpi_before.get(metric, 0)
            if before_val != 0 and imp < 0:
                regression_pct = abs(imp) / abs(before_val)
                if regression_pct > 0.2:
                    significant_worsening = True
                    break

        # Count consecutive cycles without improvement
        recent = self.get_cycles(objective_id, limit=self._max_cycles_without_improvement)
        stagnant_count = 0
        for cycle in recent:
            if cycle.improvement() <= 0:
                stagnant_count += 1
            else:
                break

        # Count consecutive negative cycles
        negative_count = 0
        for cycle in recent:
            if cycle.improvement() < 0:
                negative_count += 1
            else:
                break

        # Determine action
        if significant_worsening:
            action = FeedbackAction.PAUSE_OBJECTIVE
            analysis = (
                f"Significant worsening detected (avg_improvement={avg_improvement:.4f}). "
                f"Objective paused to prevent further damage."
            )
        elif negative_count >= 3:
            action = FeedbackAction.ESCALATE_TO_HUMAN
            analysis = (
                f"3+ consecutive negative cycles ({negative_count}). "
                f"Escalating to human for manual intervention."
            )
        elif avg_improvement < 0:
            action = FeedbackAction.CHANGE_APPROACH
            analysis = (
                f"Negative improvement ({avg_improvement:.4f}) on cycle {cycle_number}. "
                f"Current approach is not working; strategy change required."
            )
        elif stagnant_count >= self._max_cycles_without_improvement:
            action = FeedbackAction.ADJUST_STRATEGY
            analysis = (
                f"No improvement for {stagnant_count} consecutive cycles. "
                f"Adjusting strategy to break plateau."
            )
        elif avg_improvement > 0:
            action = FeedbackAction.CONTINUE
            analysis = (
                f"Positive improvement ({avg_improvement:.4f}) on cycle {cycle_number}. "
                f"Continuing current strategy."
            )
        else:
            action = FeedbackAction.CONTINUE
            analysis = (
                f"No change detected on cycle {cycle_number}. "
                f"Continuing to monitor."
            )

        return action, analysis

    @staticmethod
    def _row_to_cycle(row: sqlite3.Row) -> FeedbackCycle:
        """Convert a database row to a FeedbackCycle instance."""
        return FeedbackCycle(
            cycle_id=row["cycle_id"],
            objective_id=row["objective_id"],
            plan_id=row["plan_id"],
            cycle_number=row["cycle_number"],
            kpi_before=json.loads(row["kpi_before"]),
            kpi_after=json.loads(row["kpi_after"]),
            action_taken=FeedbackAction(row["action_taken"]),
            analysis=row["analysis"],
            timestamp=row["timestamp"],
        )


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

_closed_loop_feedback_instance: Optional[ClosedLoopFeedback] = None
_closed_loop_feedback_lock = threading.Lock()


def get_closed_loop_feedback(
    db_path: str = "autopilot_feedback.sqlite",
    max_cycles_without_improvement: int = 3,
) -> ClosedLoopFeedback:
    """Get or create the global ClosedLoopFeedback instance.

    Args:
        db_path: Path to the SQLite database file.
        max_cycles_without_improvement: Cycles without improvement before strategy adjustment.

    Returns:
        The singleton ClosedLoopFeedback instance.
    """
    global _closed_loop_feedback_instance
    with _closed_loop_feedback_lock:
        if _closed_loop_feedback_instance is None:
            _closed_loop_feedback_instance = ClosedLoopFeedback(
                db_path=db_path,
                max_cycles_without_improvement=max_cycles_without_improvement,
            )
        return _closed_loop_feedback_instance


def reset_closed_loop_feedback() -> None:
    """Reset the global ClosedLoopFeedback instance (for testing)."""
    global _closed_loop_feedback_instance
    with _closed_loop_feedback_lock:
        _closed_loop_feedback_instance = None


__all__ = [
    "FeedbackAction",
    "FeedbackCycle",
    "ClosedLoopFeedback",
    "get_closed_loop_feedback",
    "reset_closed_loop_feedback",
]
