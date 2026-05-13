"""
ZENIC-AGENTS - APA Planner v16 (Z3 Real + MCTS Real)

Planificador con MCTS real (UCB1, backpropagation, depth limiting)
y Solver real (Z3 con fallback AC-3, timeout enforcement).
"""

from .planner import APAPlanner
from ._imports import (
    ExecutionPlan, PlanStep, OperationType, RoutePath, HAS_Z3
)

__all__ = [
    "APAPlanner",
    "ExecutionPlan",
    "PlanStep",
    "OperationType",
    "RoutePath",
    "HAS_Z3",
]
