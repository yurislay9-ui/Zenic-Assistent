"""
reasoning_parts — modularized ReasoningEngine.

Public API re-exported for backward compatibility.
"""

from ._imports import (
    ReasoningMode,
    ReasoningStep,
    ReasoningResult,
    MAX_REASONING_STEPS,
    MAX_TOKENS_PER_STEP,
    MAX_REFLECT_ITERATIONS,
    REASONING_TIMEOUT_S,
    MIN_CONFIDENCE_ACCEPT,
)
from ._engine import ReasoningEngine

__all__ = [
    "ReasoningEngine",
    "ReasoningMode",
    "ReasoningStep",
    "ReasoningResult",
    "MAX_REASONING_STEPS",
    "MAX_TOKENS_PER_STEP",
    "MAX_REFLECT_ITERATIONS",
    "REASONING_TIMEOUT_S",
    "MIN_CONFIDENCE_ACCEPT",
]
