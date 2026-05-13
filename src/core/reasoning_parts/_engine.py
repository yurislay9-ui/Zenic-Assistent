"""
ReasoningEngine — main class inheriting from mixins.
"""

from typing import Any, Dict, Optional

from ._imports import ReasoningMode
from ._step_mixin import StepByStepMixin
from ._reflect_mixin import SelfReflectMixin
from ._context_mixin import ContextMixin
from ._helpers_mixin import HelpersMixin


class ReasoningEngine(HelpersMixin, ContextMixin, SelfReflectMixin, StepByStepMixin):
    """
    Motor de razonamiento avanzado para ZENIC-AGENTS.

    Extiende MiniAIEngine con modos de razonamiento que producen
    resultados más confiables a través de:

    1. Descomposición explícita del problema
    2. Auto-evaluación y corrección
    3. Inyección inteligente de contexto

    Coordina las 3 capas de IA:
      Capa 1: SemanticEngine → comprensión profunda del problema
      Capa 2: MiniAIEngine (Qwen) → razonamiento
      Capa 3: SmartMemory → experiencia previa
    """

    def __init__(self, mini_ai: Optional[Any] = None, semantic_engine: Optional[Any] = None, smart_memory: Optional[Any] = None) -> None:
        self._ai = mini_ai
        self._semantic = semantic_engine
        self._memory = smart_memory
        self._call_count = 0
        self._total_time = 0.0

    # ================================================================
    #  AUTO-SELECT BEST MODE
    # ================================================================

    def reason(self, problem: str, mode: str = "auto", context: str = "") -> "ReasoningResult":
        """
        Razonamiento automático - selecciona el mejor modo según el problema.

        Estrategia de selección:
          - Problema simple (1-2 conceptos) → step_by_step
          - Problema con posibles errores → self_reflect
          - Problema complejo con contexto → reason_with_context
          - Sin modelo → fallback determinístico
        """
        if not self._ai or not self._ai.is_loaded:
            # Even without model, honor the requested mode for result tracking
            if mode == "auto":
                return self._full_fallback(problem)
            # Return fallback with the requested mode set
            mode_map = {
                "step_by_step": ReasoningMode.STEP_BY_STEP,
                "self_reflect": ReasoningMode.SELF_REFLECT,
                "with_context": ReasoningMode.WITH_CONTEXT,
            }
            requested_mode = mode_map.get(mode, ReasoningMode.FALLBACK)
            result = self._full_fallback(problem)
            result.mode = requested_mode
            return result

        if mode != "auto":
            mode_map = {
                "step_by_step": self.step_by_step,
                "self_reflect": self.self_reflect,
                "with_context": self.reason_with_context,
            }
            selected_fn = mode_map.get(mode, self.step_by_step)
            if mode == "with_context":
                return selected_fn(problem, context)
            elif mode == "self_reflect":
                return selected_fn(problem, context=context)
            return selected_fn(problem)

        # Auto-select based on problem complexity
        complexity = self._estimate_complexity(problem)

        if complexity >= 0.7:
            # Complex: use context reasoning
            return self.reason_with_context(problem, context)
        elif complexity >= 0.4:
            # Medium: use self-reflection
            return self.self_reflect(problem, context=context)
        else:
            # Simple: use step-by-step
            return self.step_by_step(problem)

    # ================================================================
    #  STATS
    # ================================================================

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del ReasoningEngine."""
        return {
            "total_calls": self._call_count,
            "total_time_s": round(self._total_time, 2),
            "ai_available": self._ai is not None and self._ai.is_loaded,
            "semantic_available": self._semantic is not None and self._semantic.is_loaded,
            "memory_available": self._memory is not None,
            "modes": ["step_by_step", "self_reflect", "with_context", "auto"],
        }
