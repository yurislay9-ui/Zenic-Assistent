"""
ZENIC-AGENTS v1.1 - MiniAIEngine (Qwen3-0.6B Q4_K_M) - Verdict Architecture with Resilience

CAMBIO FUNDAMENTAL (v16 → v17):
  ANTES: La IA hacía 7 tareas bounded (clasificar, extraer, generar, etc.)
  AHORA: La IA SOLO emite veredictos binarios (SÍ/NO) como árbitro final.

CAMBIO v17 → v17.1:
  - Las 7 tareas bounded son 100% determinísticas (NUNCA llaman al LLM)
  - El veredicto tiene Circuit Breaker, Retry con backoff, Health Monitor
  - Multi-attempt consensus: Pregunta 3 veces, mayoría gana
  - Auditoría completa de todas las decisiones

Arquitectura de 4 capas (sin cambios estructurales):
  Capa 1: SemanticEngine → ENTIENDE (embeddings, similitud, clasificación)
  Capa 2: DeterministicPipeline → HACE (clasifica, extrae, genera, valida)
  Capa 3: EvidenceCollector + ConsensusResolver → PRUEBA y DECIDE
  Capa 4: MiniAIEngine (Qwen) → ARBITRA (solo SÍ/NO cuando hay empate) ← ESTE

Qwen ya NO es el motor principal de razonamiento.
Qwen es el ÁRBITRO que solo dice SÍ o NO cuando el sistema
determinístico no puede decidir.

7 Tareas Legacy (ahora 100% determinísticas, NUNCA llaman al LLM):
  1. classify_intent()     → Keyword scoring ponderado
  2. extract_entities()    → Regex extraction + patrones
  3. suggest_pattern()     → Lookup table + heurísticas
  4. fill_template_gaps()  → Context mapping + defaults
  5. generate_pattern()    → Template library + composición
  6. explain_violation()   → Catálogo de violaciones
  7. describe_subtask()    → Composición automática de nombre

Nuevo método principal (con resiliencia v17.1):
  verdict(question, context, evidence_for, evidence_against) → {"verdict": "YES"|"NO", ...}

Garantías (reforzadas en v17.1):
  - La IA solo puede decir SÍ o NO (cualquier otra cosa = NO)
  - Timeout = NO (principio de precaución)
  - Respuesta ambigua = NO
  - Modelo no disponible = NO
  - Circuit Breaker OPEN = NO inmediato (sin esperar timeout)
  - Multi-attempt consensus: 3 preguntas, mayoría gana
  - Es IMPOSIBLE que la IA dé una "mala respuesta" generativa

Patrones de diseño para fallos (v17.1):
  - Circuit Breaker: Protege contra LLM caído (3 fallos → OPEN)
  - Retry con exponential backoff: Reintento inteligente (base 1s, max 10s)
  - Health Monitor: Sliding window de 50 llamadas, threshold 0.3
  - Auditoría: Buffer circular de 100 entradas, detección de patrones
  - Multi-attempt consensus: 3 intentos, majority vote (threshold 2)

Optimizado para:
  - Xiaomi Redmi 12R Pro (12+8GB, MediaTek Dimensity 6100+)
  - Qwen3-0.6B Q4_K_M (378MB, ~25-30 tok/s en ARM)
  - llama-cpp-python con n_ctx=2048, n_threads=4
"""

from .mini_ai_parts import *  # noqa: F401,F403
from .mini_ai_parts import MiniAIEngine, IntentResult  # noqa: F401
from .verdict_parts import VerdictEngine, Verdict, VerdictOutput  # noqa: F401

__all__ = [
    "MiniAIEngine", "IntentResult",
    "VerdictEngine", "Verdict", "VerdictOutput",
    "MODEL_DIR", "MODEL_FILENAME", "MODEL_PATH",
    "MAX_TOKENS_CLASSIFY", "MAX_TOKENS_EXTRACT", "MAX_TOKENS_PATTERN",
    "MAX_TOKENS_TEMPLATE", "MAX_TOKENS_GENERATE", "MAX_TOKENS_EXPLAIN",
    "MAX_TOKENS_SUBTASK", "LLM_TIMEOUT_S", "N_CTX", "N_THREADS", "TEMPERATURE",
]
