"""
IntentAgent: main class inheriting all mixins.
"""

from ._imports import BaseAgent, IntentOutput
from ._mixin_prompt import PromptMixin
from ._mixin_fallback import FallbackMixin
from ._mixin_parse import ParseMixin
from ._mixin_extract import ExtractMixin
from ._mixin_api import ApiMixin


class IntentAgent(PromptMixin, ParseMixin, FallbackMixin, ExtractMixin, ApiMixin, BaseAgent[IntentOutput]):
    """
    Agente de comprensión semántica que clasifica la intención del usuario.

    Flujo de ejecución:
    1. build_prompt() → Construye prompt para el LLM con el mensaje del usuario
    2. AgentRunner.run() → Intenta LLM → parse_response()
    3. Si LLM falla → _classify_with_semantic_engine() si embeddings disponibles
    4. Si todo falla → fallback() con TF-IDF + regex determinista

    Produce siempre un IntentOutput que el Orchestrador convierte a IntentPayload.
    """

    def __init__(self, semantic_engine=None, smart_memory=None) -> None:
        BaseAgent.__init__(self, name="intent")
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory

    def wire(self, semantic_engine=None, smart_memory=None) -> None:
        """Cablea dependencias (para inyección post-creación)."""
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory
