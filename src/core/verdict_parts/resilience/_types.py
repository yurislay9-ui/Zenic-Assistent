"""
Verdict Resilience Patterns — Circuit Breaker, Retry, Health Monitor, Auditor.

Patrones de diseño para hacer que el sistema de veredicto sea resiliente
ante fallos de la IA (Qwen3-0.6B):

  1. VerdictCircuitBreaker: Protege contra fallos en cascada del LLM.
     - Si el LLM falla N veces consecutivas → OPEN (no se llama al LLM)
     - Después de recovery_timeout → HALF_OPEN (prueba 1 llamada)
     - Si funciona → CLOSED (vuelve a normal)
     - Si falla → OPEN de nuevo

  2. VerdictRetryPolicy: Reintento con exponential backoff.
     - Máximo N intentos con delays crecientes
     - Jitter aleatorio para evitar thundering herd
     - Callbacks de progreso para logging

  3. VerdictHealthMonitor: Monitorea la salud del LLM.
     - Latencia promedio, tasa de éxito, última respuesta
     - Auto-disable si la salud es críticamente baja
     - Recuperación automática cuando la salud mejora

  4. VerdictAuditor: Registro de auditoría de todos los veredictos.
     - Almacena cada veredicto con contexto y evidencia
     - Permite análisis post-mortem
     - Detecta patrones de fallo

Optimizado para:
  - Xiaomi Redmi 12R Pro (12+8GB, MediaTek Dimensity 6100+)
  - Qwen3-0.6B Q4_K_M (378MB, ~25-30 tok/s en ARM)
  - Memoria máxima: < 1MB para auditoría (buffer circular)
"""

import time
import random
import logging
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
from collections import deque

logger = logging.getLogger("zenic_agents.verdict_parts.resilience")


# ============================================================
#  VERDICT CIRCUIT BREAKER
# ============================================================

class VerdictCircuitState(str, Enum):
    """Estados del Circuit Breaker para veredictos."""
    CLOSED = "closed"         # Normal: LLM se usa cuando se necesita
    OPEN = "open"             # LLM no se llama: fallos consecutivos
    HALF_OPEN = "half_open"   # Probando si el LLM se recuperó


