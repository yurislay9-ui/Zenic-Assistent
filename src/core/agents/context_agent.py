"""
ZENIC-AGENTS - ContextAgent (F3) — Facade

Agente gestor de ventana de contexto que UNIFICA y OPTIMIZA la gestión
de contexto dispersa en múltiples subsistemas.

This module is a thin facade; all logic lives in context_agent_parts/.
"""

from .context_agent_parts import *  # noqa: F401,F403
from .context_agent_parts import (
    ContextAgent, TOTAL_CONTEXT_BUDGET, DEFAULT_TOKEN_BUDGET,
    ContextEntry, ContextOutput, IntentOutput,
)

__all__ = [
    "ContextAgent",
    "TOTAL_CONTEXT_BUDGET",
    "DEFAULT_TOKEN_BUDGET",
    "RECENCY_DECAY_FACTOR",
    "OP_RELEVANCE_WEIGHTS",
    "GOAL_RELEVANCE_WEIGHTS",
    "MAX_ENTRIES_FOR_SCORING",
    "MAX_PREFETCH_RESULTS",
    "ContextEntry",
    "ContextOutput",
    "IntentOutput",
]
