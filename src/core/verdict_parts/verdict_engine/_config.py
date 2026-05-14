"""
VerdictEngine - El único punto donde la IA interviene, y solo emite SÍ o NO.

PRINCIPIO FUNDAMENTAL:
  La IA NUNCA genera, NUNCA clasifica, NUNCA valida, NUNCA explica.
  La IA SOLO responde una pregunta binaria cuando el sistema
  determinístico no puede decidir.

v17.1 MEJORAS DE RESILIENCIA:
  - Circuit Breaker: Protege contra fallos en cascada del LLM
  - Retry con exponential backoff: Recuperación de errores transitorios
  - Health Monitor: Seguimiento de salud del LLM en tiempo real
  - VerdictAuditor: Registro de auditoría de todas las decisiones
  - Multi-attempt consensus: Pregunta N veces, mayoría gana
  - Timeout cascade protection: Si el LLM está lento, se adapta
  - Fallback gradual: Consenso → LLM simple → LLM consensus → NO

Flujo del Veredicto (v17.1):
  1. DeterministicPipeline ejecuta todas las tareas
  2. EvidenceCollector recolecta evidencia
  3. ConsensusResolver evalúa consenso
  4. Si consenso ≥ HIGH → Decisión sin IA
  5. Si consenso < HIGH → VerdictEngine pide a Qwen:
     a. Check Circuit Breaker → si OPEN, fallback NO
     b. Check Health Monitor → si unhealthy, warning
     c. Multi-attempt consensus (3 intentos, mayoría gana)
     d. Si funciona → Audit y retornar
     e. Si falla → Retry con backoff (máx 3 veces)
     f. Si todo falla → Fallback NO (principio de precaución)

Garantías contra errores:
  - La IA solo puede responder "YES" o "NO" (cualquier otra cosa = NO)
  - Si la IA no responde en 5 segundos → Default conservador (NO)
  - Si la IA da una respuesta ambigua → Se cuenta como NO
  - Circuit Breaker evita llamadas cuando el LLM está caído
  - Health Monitor detecta degradación gradual
  - Auditoría permite análisis post-mortem
"""

import os
import re
import time
import logging
import concurrent.futures
from typing import Optional, Dict, Any, List

from ..types import (
    EvidenceType,
    Verdict, Evidence, VerdictInput, VerdictOutput,
    ConsensusResult, VerdictConfidence,
)
from ..evidence_collector import EvidenceCollector
from ..consensus_resolver import ConsensusResolver
from ..deterministic_pipeline import DeterministicPipeline

# Import resilience patterns
try:
    from ..resilience import (
        VerdictCircuitBreaker,
        VerdictRetryConfig,
        VerdictHealthMonitor,
        VerdictAuditor,
        VerdictAuditEntry,
        VerdictResilienceOrchestrator,
    )
    _RESILIENCE_AVAILABLE = True
except ImportError:
    _RESILIENCE_AVAILABLE = False

logger = logging.getLogger("zenic_agents.verdict_parts.verdict_engine")

# === Configuración del VerdictEngine ===
VERDICT_TIMEOUT_S = 5.0           # Timeout estricto para la IA (5 segundos)
VERDICT_MAX_TOKENS = 10           # Solo necesita 1 token, damos margen
VERDICT_TEMPERATURE = 0.0         # 0.0 = determinismo absoluto
VERDICT_MAX_RETRIES = 3           # Reintentos con exponential backoff (antes 1)
VERDICT_CONSENSUS_ATTEMPTS = int(os.environ.get("ZENIC_VERDICT_CONSENSUS", "1"))  # ARM: 1 attempt (was 3, too many LLM timeouts on ARM)
VERDICT_CONSENSUS_THRESHOLD = 2   # Mínimo de YES para verdict YES

VERDICT_PROMPT_TEMPLATE = """You are a binary decision maker. Based on the evidence below, answer with ONLY one word: YES or NO.

Evidence FOR: {evidence_for}
Evidence AGAINST: {evidence_against}
Consensus score: {score:.2f} (-1=NO, +1=YES)
Question: {question}

Answer with ONLY: YES or NO"""

FALLBACK_PROMPT_TEMPLATE = """Should this be approved? Answer ONLY: YES or NO

Context: {context}
Evidence summary: {summary}

Answer:"""
