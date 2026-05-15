"""
A40 DeterministicPipeline — Execute all 7 deterministic tasks without AI.

DEPRECATED: This agent violates the SRP invariant (7 tasks in 1 agent).
Individual A01-A04 agents should be used instead.
"""

from ._core import DeterministicPipeline
from ._constants import (
    EXT_LANG_MAP, OP_KEYWORDS, GOAL_KEYWORDS,
    PATTERN_HEURISTICS, PATTERN_LIBRARY,
    VIOLATION_CATALOG, GAP_DEFAULTS,
)

__all__ = [
    "DeterministicPipeline",
    "EXT_LANG_MAP", "OP_KEYWORDS", "GOAL_KEYWORDS",
    "PATTERN_HEURISTICS", "PATTERN_LIBRARY",
    "VIOLATION_CATALOG", "GAP_DEFAULTS",
]
