"""
criticality_agent_parts — modularized CriticalityAgent (F4).

Public API re-exported for backward compatibility.
"""

from ._agent import CriticalityAgent
from ._imports import (
    LEVEL_FAST, LEVEL_MODERATE, LEVEL_SURGICAL,
    STR_TO_LEVEL, LEVEL_TO_PATH,
    CRITICALITY_ADJUSTMENTS,
    GOAL_CRITICALITY_MAP, OP_CRITICALITY_MAP,
    CRITICAL_KEYWORDS, MODERATE_KEYWORDS,
)

__all__ = [
    "CriticalityAgent",
    "LEVEL_FAST",
    "LEVEL_MODERATE",
    "LEVEL_SURGICAL",
    "STR_TO_LEVEL",
    "LEVEL_TO_PATH",
    "CRITICALITY_ADJUSTMENTS",
    "GOAL_CRITICALITY_MAP",
    "OP_CRITICALITY_MAP",
    "CRITICAL_KEYWORDS",
    "MODERATE_KEYWORDS",
]
