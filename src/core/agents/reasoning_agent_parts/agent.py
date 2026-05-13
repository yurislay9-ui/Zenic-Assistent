"""
ReasoningAgent: main class inheriting all mixins.
"""

from ._imports import BaseAgent, ReasoningOutput
from ._mixin_prompt import PromptMixin
from ._mixin_fallback import FallbackMixin
from ._mixin_parse import ParseMixin
from ._mixin_api import ApiMixin


class ReasoningAgent(PromptMixin, ParseMixin, FallbackMixin, ApiMixin, BaseAgent[ReasoningOutput]):
    """
    Agente de razonamiento avanzado que unifica ReasoningEngine + ThinkingEngine.

    Flujo de ejecución:
    1. build_prompt() → Construye prompt según modo (step_by_step/self_reflect/with_context)
    2. AgentRunner.run() → Intenta LLM → parse_response()
    3. Si LLM falla → fallback con razonamiento determinista
    4. Contexto inyectado desde SmartMemory + SemanticEngine

    Modos de razonamiento:
    - step_by_step: Descompone el problema en pasos explícitos
    - self_reflect: Genera → evalúa → refina (más confiable, más costoso)
    - with_context: Razonamiento con inyección de memoria + semántica
    """

    def __init__(self, semantic_engine=None, smart_memory=None) -> None:
        BaseAgent.__init__(self, name="reasoning")
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory

    def wire(self, semantic_engine=None, smart_memory=None) -> None:
        """Cablea dependencias (para inyección post-creación)."""
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory
