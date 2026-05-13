"""
ThinkingEngine — facade re-exporting all sub-modules.

Backward-compatible: ``from src.core.thinking_engine import ThinkingEngine, GenerationPlan``
still works exactly as before.
"""

from ._imports import (
    logger, APP_TEMPLATES, AUTOMATION_TEMPLATES,
    GenerationPlan, ThinkingResult, Optional, Any,
)
from ._context_mixin import ContextMixin
from ._planning_mixin import PlanningMixin
from ._reasoning_mixin import ReasoningMixin


class ThinkingEngine(ContextMixin, PlanningMixin, ReasoningMixin):
    """
    Motor principal de razonamiento - El CEREBRO del sistema.

    Coordina las 3 capas de IA:
      Capa 1: SemanticEngine → ENTIENDE
      Capa 2: MiniAIEngine (Qwen) → PIENSA
      Capa 3: SmartMemory → RECUERDA
    """

    def __init__(self, mini_ai=None, semantic_engine=None, smart_memory=None) -> None:
        self._ai = mini_ai
        self._semantic = semantic_engine
        self._memory = smart_memory
        self._call_count = 0
        self._thinking_time = 0.0


__all__ = [
    "ThinkingEngine",
    "GenerationPlan",
    "ThinkingResult",
    "APP_TEMPLATES",
    "AUTOMATION_TEMPLATES",
]
