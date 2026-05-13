"""
AutomationAgent: main class inheriting all mixins.
"""

from ._imports import BaseAgent, AutomationOutput
from ._mixin_prompt import PromptMixin
from ._mixin_fallback import FallbackMixin
from ._mixin_parse import ParseMixin
from ._mixin_api import ApiMixin


class AutomationAgent(PromptMixin, ParseMixin, FallbackMixin, ApiMixin, BaseAgent[AutomationOutput]):
    """
    Agente de diseño de automatizaciones que unifica la inferencia
    de triggers, acciones y schedules desde lenguaje natural.

    Flujo de ejecución:
    1. build_prompt() → Construye prompt con descripción de automatización
    2. AgentRunner.run() → Intenta LLM → parse_response()
    3. Si LLM falla → fallback determinista por keywords

    El agente reemplaza:
    - AutomationEngine._infer_trigger() (keyword matching, 30 líneas)
    - AutomationEngine._infer_actions() (keyword matching, 55 líneas)
    - AutomationEngine._parse_schedule() (regex parsing, 25 líneas)
    - AutomationEngine._extract_name() (simple extraction, 5 líneas)
    """

    def __init__(self, semantic_engine=None, smart_memory=None) -> None:
        BaseAgent.__init__(self, name="automation")
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory

    def wire(self, semantic_engine=None, smart_memory=None) -> None:
        """Cablea dependencias."""
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory
