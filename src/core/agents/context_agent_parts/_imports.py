"""
Shared imports and constants for context_agent_parts.
"""

import re
import time
import json
import math
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import IntentOutput, ContextEntry, ContextOutput

logger = logging.getLogger(__name__)

# ── Constantes de presupuesto de tokens ──

# Presupuesto total de contexto para agentes (de 600 tokens del LLM)
# Se reserva ~100 tokens para system prompt + instrucciones
TOTAL_CONTEXT_BUDGET = 500

# Distribución por defecto del presupuesto
DEFAULT_TOKEN_BUDGET: Dict[str, int] = {
    "intent": 50,        # SurgicalAgent necesita poco contexto
    "reasoning": 150,    # ReasoningAgent necesita más para razonar
    "code": 200,         # CodeAgent necesita el máximo
    "validation": 100,   # ValidationAgent necesita contexto del código
    "reserve": 100,      # Buffer para contexto dinámico
}

# Factor de decaimiento temporal (entradas recientes > antiguas)
RECENCY_DECAY_FACTOR = 0.95  # Por cada 60 segundos de antigüedad

# Pesos de relevancia por operation (cuánto importa cada operation para scoring)
OP_RELEVANCE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "CREATE":    {"CREATE": 1.0, "OPTIMIZE": 0.6, "REFACTOR": 0.5, "DEBUG": 0.3},
    "REFACTOR":  {"REFACTOR": 1.0, "OPTIMIZE": 0.7, "CREATE": 0.4, "DEBUG": 0.3},
    "DELETE":    {"DELETE": 1.0, "REFACTOR": 0.5, "DEBUG": 0.4, "ANALYZE": 0.3},
    "SEARCH":    {"SEARCH": 1.0, "ANALYZE": 0.7, "EXPLAIN": 0.5, "DEBUG": 0.2},
    "ANALYZE":   {"ANALYZE": 1.0, "SEARCH": 0.6, "EXPLAIN": 0.5, "DEBUG": 0.3},
    "EXPLAIN":   {"EXPLAIN": 1.0, "ANALYZE": 0.6, "SEARCH": 0.4, "DEBUG": 0.2},
    "DEBUG":     {"DEBUG": 1.0, "ANALYZE": 0.5, "REFACTOR": 0.4, "DELETE": 0.3},
    "OPTIMIZE":  {"OPTIMIZE": 1.0, "REFACTOR": 0.7, "CREATE": 0.3, "DEBUG": 0.3},
}

# Pesos de relevancia por goal
GOAL_RELEVANCE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "BUG_FIX":             {"BUG_FIX": 1.0, "SECURITY_HARDEN": 0.6, "PERFORMANCE": 0.4},
    "FEATURE_ADD":         {"FEATURE_ADD": 1.0, "MODERN_PATTERN": 0.5, "COMPLEXITY_REDUCTION": 0.3},
    "SECURITY_HARDEN":     {"SECURITY_HARDEN": 1.0, "BUG_FIX": 0.7, "PERFORMANCE": 0.3},
    "PERFORMANCE":         {"PERFORMANCE": 1.0, "OPTIMIZE": 0.6, "COMPLEXITY_REDUCTION": 0.5},
    "COMPLEXITY_REDUCTION":{"COMPLEXITY_REDUCTION": 1.0, "READABILITY": 0.7, "REFACTOR": 0.5},
    "MODERN_PATTERN":      {"MODERN_PATTERN": 1.0, "FEATURE_ADD": 0.5, "READABILITY": 0.4},
    "READABILITY":         {"READABILITY": 1.0, "COMPLEXITY_REDUCTION": 0.7, "MODERN_PATTERN": 0.4},
}

# Máximo de entradas de memoria a considerar para scoring
MAX_ENTRIES_FOR_SCORING = 30

# Máximo de memorias pre-fetched por intent
MAX_PREFETCH_RESULTS = 5

# Note: ContextEntry and ContextOutput are imported from schemas.py (single source of truth)
