"""
MiniAIEngine sub-package — Qwen3-0.6B verdict-only engine (v17.1).

Motor de VEREDICTO - La IA solo dice SÍ o NO.

v17.1: Las 7 tareas bounded son 100% determinísticas.
       Solo verdict() usa el LLM, con resiliencia completa.
"""

from ._imports import (
    MODEL_DIR, MODEL_FILENAME, MODEL_PATH,
    MAX_TOKENS_CLASSIFY, MAX_TOKENS_EXTRACT, MAX_TOKENS_PATTERN,
    MAX_TOKENS_TEMPLATE, MAX_TOKENS_GENERATE, MAX_TOKENS_EXPLAIN,
    MAX_TOKENS_SUBTASK, LLM_TIMEOUT_S, N_CTX, N_THREADS, TEMPERATURE,
    IntentResult,
)
from ._lifecycle import ModelLifecycleMixin
from ._tasks import BoundedTasksMixin
from ._fallbacks import FallbackMethodsMixin
from ._engine import MiniAIEngine

__all__ = [
    "MODEL_DIR", "MODEL_FILENAME", "MODEL_PATH",
    "MAX_TOKENS_CLASSIFY", "MAX_TOKENS_EXTRACT", "MAX_TOKENS_PATTERN",
    "MAX_TOKENS_TEMPLATE", "MAX_TOKENS_GENERATE", "MAX_TOKENS_EXPLAIN",
    "MAX_TOKENS_SUBTASK", "LLM_TIMEOUT_S", "N_CTX", "N_THREADS", "TEMPERATURE",
    "IntentResult",
    "ModelLifecycleMixin",
    "BoundedTasksMixin",
    "FallbackMethodsMixin",
    "MiniAIEngine",
]
