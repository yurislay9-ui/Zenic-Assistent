"""
SurgicalAgent main class — inherits from all mixins.
"""

from ._imports import BaseAgent, IntentOutput, VALID_OPERATIONS
from ._base import BaseInterfaceMixin
from ._cables import CablesMixin
from ._extractors import ExtractorsMixin


class SurgicalAgent(BaseInterfaceMixin, CablesMixin, ExtractorsMixin, BaseAgent[IntentOutput]):
    """
    Agente quirúrgico F2: Clasificación de intención con fusión multi-señal.

    Flujo de ejecución (4 cables, en orden de costo ascendente):
    1. SmartMemory cache → Si hit, retorno inmediato (0ms LLM)
    2. SemanticEngine → Si embeddings disponibles y conf > 0.4, fusión con TF-IDF
    3. LLM via AgentRunner → Si disponible, intenta clasificación con Qwen3
    4. TF-IDF determinista → Siempre funciona, sin dependencias

    Fusión: Cuando múltiples señales coinciden, la confianza se calibra al alza.
    Cuando discrepan, la confianza se calibra a la baja.

    Reemplaza:
    - IntentAgent original (594 líneas) → SurgicalAgent (~250 líneas)
    - SemanticParser.classify() (Level 1)
    - MiniAIEngine.classify_intent()
    - SemanticEngine._fallback_classify()
    """

    def __init__(self, semantic_engine=None, smart_memory=None) -> None:
        super().__init__(name="surgical")
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory
        # Calibración adaptativa: trackea aciertos por operation
        self._calibration: Dict[str, Dict[str, int]] = {
            op: {"hits": 0, "misses": 0} for op in VALID_OPERATIONS
        }

    def wire(self, semantic_engine=None, smart_memory=None) -> None:
        """Cablea dependencias (inyección post-creación)."""
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory
