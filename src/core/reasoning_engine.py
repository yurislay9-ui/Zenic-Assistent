"""
ZENIC-AGENTS - ReasoningEngine (Phase 8.1) — Facade

Motor de RAZONAMIENTO AVANZADO que va más allá de las tareas bounded de MiniAI.

This module is a thin facade; all logic lives in reasoning_parts/.
"""

from .reasoning_parts import *  # noqa: F401,F403
from .reasoning_parts import ReasoningEngine, ReasoningMode, ReasoningResult

__all__ = [
    "ReasoningEngine",
    "ReasoningMode",
    "ReasoningStep",
    "ReasoningResult",
    "MAX_REASONING_STEPS",
    "MAX_TOKENS_PER_STEP",
    "MAX_REFLECT_ITERATIONS",
    "REASONING_TIMEOUT_S",
    "MIN_CONFIDENCE_ACCEPT",
]
