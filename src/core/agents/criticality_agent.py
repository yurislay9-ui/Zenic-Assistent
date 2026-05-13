"""
ZENIC-AGENTS - CriticalityAgent (F4) — Facade

Agente de Ruteo Dinámico de Criticalidad que UNIFICA la lógica de
criticalidad dispersa en 5 subsistemas.

This module is a thin facade; all logic lives in criticality_agent_parts/.
"""

from .criticality_agent_parts import *  # noqa: F401,F403
from .criticality_agent_parts import (
    CriticalityAgent, LEVEL_FAST, LEVEL_MODERATE, LEVEL_SURGICAL,
    STR_TO_LEVEL, LEVEL_TO_PATH, CRITICALITY_ADJUSTMENTS,
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
