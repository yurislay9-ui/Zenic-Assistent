"""
MiniAIEngine bounded task methods (tasks 1-7) — PURELY DETERMINISTIC.

CAMBIO FUNDAMENTAL (v17.1):
  ANTES: Las 7 tareas llamaban _call_llm() primero, luego fallback.
  AHORA: Las 7 tareas son 100% determinísticas. NUNCA llaman al LLM.

  La IA SOLO se usa para veredictos binarios (SÍ/NO) vía VerdictMixin.
  Esto elimina:
    - Latencia de 3-8s por tarea
    - Alucinaciones en clasificación/extracción/generación
    - Parsing errors del output del LLM
    - Uso innecesario del modelo Qwen3-0.6B

  Las 7 tareas ahora delegan al DeterministicPipeline cuando está
  disponible, o usan métodos fallback propios cuando no.
"""

import re
import os
import json
import logging
from typing import Optional, Any
from .._imports import IntentResult
from src.core.shared.constants import VALID_INTENT_OPERATIONS, VALID_INTENT_GOALS, EXT_LANG_MAP


logger = logging.getLogger(__name__)


