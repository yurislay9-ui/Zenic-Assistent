"""
ZENIC-AGENTS v1.1 - Verdict Architecture with Resilience

La IA ya NO hace tareas. Solo emite el veredicto final.

Arquitectura de 4 capas:
  Capa 1: DeterministicPipeline → HACE (clasifica, extrae, genera, valida)
  Capa 2: EvidenceCollector → PRUEBA (recolecta evidencia a favor y en contra)
  Capa 3: ConsensusResolver → DECIDE (consenso multi-señal sin IA)
  Capa 4: VerdictEngine → ARBITRA (Qwen solo si hay empate: SÍ o NO)

v17.1 Resilience Patterns:
  - VerdictCircuitBreaker: Protege contra fallos en cascada del LLM
  - VerdictRetryConfig: Reintento con exponential backoff + jitter
  - VerdictHealthMonitor: Seguimiento de salud del LLM
  - VerdictAuditor: Registro de auditoría de todas las decisiones
  - VerdictResilienceOrchestrator: Orquestador de todos los patrones
  - Multi-attempt consensus: Pregunta N veces, mayoría gana

Principio: La IA nunca genera, nunca clasifica, nunca valida.
La IA solo responde una pregunta binaria cuando el sistema determinístico no puede.
"""

from .types import (
    Verdict, Evidence, EvidenceType, VerdictInput, VerdictOutput,
    ConsensusResult, DeterministicResult, VerdictConfidence,
)
from .evidence_collector import EvidenceCollector
from .consensus_resolver import ConsensusResolver
from .deterministic_pipeline import DeterministicPipeline
from .verdict_engine import VerdictEngine

# v17.1: Resilience patterns
try:
    from .resilience import (
        VerdictCircuitBreaker, VerdictCircuitState,
        VerdictRetryConfig,
        VerdictHealthMonitor, VerdictHealthSnapshot,
        VerdictAuditor, VerdictAuditEntry,
        VerdictResilienceOrchestrator,
    )
    _RESILIENCE_EXPORTS = [
        "VerdictCircuitBreaker", "VerdictCircuitState",
        "VerdictRetryConfig",
        "VerdictHealthMonitor", "VerdictHealthSnapshot",
        "VerdictAuditor", "VerdictAuditEntry",
        "VerdictResilienceOrchestrator",
    ]
except ImportError:
    _RESILIENCE_EXPORTS = []

__all__ = [
    "Verdict", "Evidence", "EvidenceType", "VerdictInput", "VerdictOutput",
    "ConsensusResult", "DeterministicResult", "VerdictConfidence",
    "EvidenceCollector", "ConsensusResolver", "DeterministicPipeline",
    "VerdictEngine",
]
__all__.extend(_RESILIENCE_EXPORTS)  # type: ignore[misc]
