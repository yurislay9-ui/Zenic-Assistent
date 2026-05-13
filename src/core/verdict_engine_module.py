"""
ZENIC-AGENTS v1 - Verdict Architecture

La IA ya NO hace tareas. Solo emite el veredicto final: SÍ o NO.

Arquitectura de 4 capas:
  Capa 1: DeterministicPipeline → HACE (clasifica, extrae, genera, valida)
  Capa 2: EvidenceCollector → PRUEBA (recolecta evidencia a favor y en contra)
  Capa 3: ConsensusResolver → DECIDE (consenso multi-señal sin IA)
  Capa 4: VerdictEngine → ARBITRA (Qwen solo si hay empate: SÍ o NO)

Uso principal:
  engine = VerdictEngine(mini_ai=qwen_engine)
  result = engine.verdict("Crear función de autenticación", code, "python")
  print(result.verdict)  # YES o NO
  print(result.llm_used)  # True solo si se necesitó la IA

Antes (v16): La IA hacía 7 tareas + 6 agentes + 3 motores la llamaban
Ahora (v17): La IA solo responde SÍ/NO cuando hay empate en el consenso
"""

from .verdict_parts import (
    Verdict, Evidence, EvidenceType, VerdictInput, VerdictOutput,
    ConsensusResult, DeterministicResult, VerdictConfidence,
    EvidenceCollector, ConsensusResolver, DeterministicPipeline,
    VerdictEngine,
)

__all__ = [
    "Verdict", "Evidence", "EvidenceType", "VerdictInput", "VerdictOutput",
    "ConsensusResult", "DeterministicResult", "VerdictConfidence",
    "EvidenceCollector", "ConsensusResolver", "DeterministicPipeline",
    "VerdictEngine",
]
