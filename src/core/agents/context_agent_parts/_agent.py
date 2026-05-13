"""
ContextAgent — main class inheriting from mixins.
"""

from typing import Any, Dict

from ._imports import BaseAgent, ContextOutput
from ._cables_mixin import CablesMixin
from ._core_mixin import CoreMixin


class ContextAgent(CablesMixin, CoreMixin, BaseAgent[ContextOutput]):
    """
    Agente F3: Gestor de ventana de contexto con compresión adaptativa.

    Flujo de ejecución (4 cables, en orden de costo ascendente):
    1. SmartMemory + scoring → Seleccionar entradas relevantes
    2. TF-IDF compression → Comprimir si no hay LLM
    3. LLM compression → Resumen semántico si Qwen disponible
    4. Token budget → Asignar presupuesto a cada agente downstream
    """

    def __init__(self, semantic_engine=None, smart_memory=None) -> None:
        super().__init__(name="context")
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory

        # Cache de contexto compartido (deduplicación cross-agent)
        # Each entry stores (compressed_context, timestamp) for per-entry TTL
        self._shared_context_cache: Dict[str, tuple] = {}
        self._shared_context_ttl: float = 30.0  # 30 segundos de TTL

        # Track de qué contexto ya se envió a cada agente (deduplicación)
        self._agent_context_sent: Dict[str, set] = {}

        # Estadísticas de presupuesto de tokens
        self._budget_usage: Dict[str, Dict[str, int]] = {}

        # Open Design: Design System preservation mode
        self._design_system_mode: bool = False
        self._design_system_budget_multiplier: float = 1.0

    def wire(self, semantic_engine=None, smart_memory=None) -> None:
        """Cablea dependencias (inyección post-creación)."""
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory

        # Open Design: propagate design system mode
        try:
            from src.core.open_design.config import get_open_design_config
            od_config = get_open_design_config()
            if od_config.preserve_design_systems:
                self._design_system_mode = True
                self._design_system_budget_multiplier = od_config.design_system_budget_multiplier
        except ImportError:
            pass

    def set_design_system_mode(self, enabled: bool = False,
                                budget_multiplier: float = 1.0) -> None:
        """Open Design: Enable/disable Design System preservation mode.

        When enabled, the ContextAgent will NOT truncate Design System
        prompts from Open Design, preserving the full design specification
        for accurate UI generation.
        """
        self._design_system_mode = enabled
        self._design_system_budget_multiplier = budget_multiplier
