"""
ZENIC-AGENTS - Autopilot Planner (Phase D1)

Decomposes objectives into actionable automation steps with dependency
tracking, risk levels, and impact estimation. Uses built-in templates
for common business objectives with a generic fallback.

Thread-safe: All public methods guarded by RLock.
Retry logic: DB operations wrapped with 3 retries, base 0.5s backoff.

This package re-exports all public symbols from its submodules so that
``from src.core.autopilot.planner import ...`` continues to work exactly
as before the modular split.
"""

from src.core.autopilot.planner._optimizer import estimate_plan_impact
from src.core.autopilot.planner._planner import (
    AutopilotPlanner,
    get_autopilot_planner,
    reset_autopilot_planner,
)
from src.core.autopilot.planner._scheduler import (
    _GENERIC_PLAN_TEMPLATE,
    _PLAN_TEMPLATES,
    _match_template,
)
from src.core.autopilot.planner._types import PlanStep, PlannedAction

__all__ = [
    "PlanStep",
    "PlannedAction",
    "AutopilotPlanner",
    "get_autopilot_planner",
    "reset_autopilot_planner",
]
