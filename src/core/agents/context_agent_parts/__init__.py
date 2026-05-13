"""
context_agent_parts — modularized ContextAgent (F3).

Public API re-exported for backward compatibility.
"""

from ._agent import ContextAgent
from ._imports import (
    TOTAL_CONTEXT_BUDGET,
    DEFAULT_TOKEN_BUDGET,
    RECENCY_DECAY_FACTOR,
    OP_RELEVANCE_WEIGHTS,
    GOAL_RELEVANCE_WEIGHTS,
    MAX_ENTRIES_FOR_SCORING,
    MAX_PREFETCH_RESULTS,
    ContextEntry,
    ContextOutput,
    IntentOutput,
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
