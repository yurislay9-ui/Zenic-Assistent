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

import logging as _logging

# ── Verdict Output Validation (H-88 fix) ──────────────────
VALID_VERDICTS = {"YES", "NO"}

_logger = _logging.getLogger(__name__)


def _validate_ai_verdict(raw_output: str) -> str:
    """Validate that AI output is strictly binary (YES/NO).

    INVARIANT: The AI can ONLY say YES or NO.
    Any other output is treated as NO (precautionary principle).

    Args:
        raw_output: Raw text from the AI model.

    Returns:
        "YES" or "NO" — never any other value.
    """
    if not raw_output or not raw_output.strip():
        return "NO"

    clean = raw_output.strip().upper()

    # Check for exact match first
    if clean in VALID_VERDICTS:
        return clean

    # Check for partial match (AI might add explanation after verdict)
    first_word = clean.split()[0] if clean.split() else ""
    if first_word in VALID_VERDICTS:
        _logger.warning(
            "VerdictEngine: AI added extra output after verdict. "
            "Using first word only: %s (raw: %s)",
            first_word, raw_output[:100],
        )
        return first_word

    # Invalid output → default to NO (precautionary principle)
    _logger.error(
        "VerdictEngine: AI produced non-binary output: %s. "
        "Defaulting to NO (precautionary principle).",
        raw_output[:100],
    )
    return "NO"


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
    "_validate_ai_verdict", "VALID_VERDICTS",
]
