"""
ZENIC-AGENTS - Autopilot Planner Optimization Utilities

Retry helper for database operations and plan impact estimation
with dependency-weighted scoring.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any, Dict, Optional

from src.core.autopilot.planner._types import PlannedAction

logger = logging.getLogger(__name__)


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
#  IMPACT ESTIMATION
# ──────────────────────────────────────────────────────────────

def estimate_plan_impact(plan: PlannedAction) -> float:
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
