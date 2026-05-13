"""Shared imports for planner_parts.

FIX (Phase 4): Removed unused import (ConstraintSolver) that is never
consumed by child modules via `from ._imports import`. Only the names
actually used by planner_parts modules are imported.
"""

import uuid
import time
import logging
import gc

from src.core.shared.contracts import (
    ExecutionPlan, PlanStep, OperationType, RoutePath,
    MCTSPlanner, Z3Solver, TimeoutEnforcer,
    CodeConstraintBuilder, Constraint, HAS_Z3
)
from src.config.loader import (
    load_settings, get_solver_timeout_ms, get_solver_fast_timeout_ms,
    get_mcts_config, get_k_path_limit
)
from src.core.shared.resource_governor import get_governor

logger = logging.getLogger(__name__)

__all__ = ["uuid", "time", "gc", "logger",
           "ExecutionPlan", "PlanStep", "OperationType", "RoutePath",
           "MCTSPlanner", "Z3Solver", "TimeoutEnforcer",
           "CodeConstraintBuilder", "Constraint", "HAS_Z3",
           "load_settings", "get_solver_timeout_ms", "get_solver_fast_timeout_ms",
           "get_mcts_config", "get_k_path_limit", "get_governor"]
