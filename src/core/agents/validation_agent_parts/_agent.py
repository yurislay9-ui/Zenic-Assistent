"""
ValidationAgent main class — inherits from all mixins.
"""

from ._imports import BaseAgent, ValidationOutput
from ._base import BaseInterfaceMixin
from ._code_validation import CodeValidationMixin
from ._chain_config import ChainConfigValidationMixin
from ._helpers import HelpersMixin


class ValidationAgent(BaseInterfaceMixin, CodeValidationMixin,
                      ChainConfigValidationMixin, HelpersMixin, BaseAgent[ValidationOutput]):
    """
    Agente de validación que unifica ChainValidator + code quality checks.

    Flujo de ejecución:
    1. build_prompt() → Construye prompt según tipo de target
    2. AgentRunner.run() → Intenta LLM → parse_response()
    3. Si LLM falla → fallback determinista por reglas estáticas

    El agente unifica la lógica que antes estaba en:
    - ChainValidator.validate() (250 líneas)
    - CodeTransformer bug detection (partial)
    """

    def __init__(self, semantic_engine=None, smart_memory=None) -> None:
        super().__init__(name="validation")
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory

    def wire(self, semantic_engine=None, smart_memory=None) -> None:
        """Cablea dependencias."""
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory
