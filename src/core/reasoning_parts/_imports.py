"""
Shared imports, types, and constants for reasoning_parts.
"""

import re
import json
import time
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# === Reasoning Configuration ===
MAX_REASONING_STEPS = 3
MAX_TOKENS_PER_STEP = 250
MAX_REFLECT_ITERATIONS = 2
REASONING_TIMEOUT_S = 20.0
MIN_CONFIDENCE_ACCEPT = 0.5  # Minimum confidence to accept a reasoning result


class ReasoningMode(Enum):
    """Available reasoning modes."""
    STEP_BY_STEP = "step_by_step"
    SELF_REFLECT = "self_reflect"
    WITH_CONTEXT = "with_context"
    FALLBACK = "fallback"


@dataclass
class ReasoningStep:
    """A single step in a reasoning chain."""
    step_number: int
    thought: str = ""
    conclusion: str = ""
    confidence: float = 0.0
    duration_ms: float = 0.0
    source: str = "llm"  # "llm" or "fallback"


@dataclass
class ReasoningResult:
    """Result of a complete reasoning operation."""
    answer: str = ""
    confidence: float = 0.0
    mode: ReasoningMode = ReasoningMode.FALLBACK
    steps: List[ReasoningStep] = field(default_factory=list)
    total_duration_ms: float = 0.0
    refinements: int = 0
    context_used: bool = False
    memory_hits: int = 0
    source: str = "fallback"  # "llm", "fallback", "semantic"
