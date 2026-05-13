"""
ZENIC-AGENTS - IntentAgent (Facade)

Thin facade — all logic lives in intent_agent_parts/.
"""

from .intent_agent_parts import *  # noqa: F401,F403
from .intent_agent_parts import (
    IntentAgent, CRITICALITY_KEYWORDS,
    VALID_OPERATIONS, VALID_GOALS,
)

__all__ = [
    "CRITICALITY_KEYWORDS",
    "VALID_OPERATIONS",
    "VALID_GOALS",
    "VALID_LANGUAGES",
    "OP_KEYWORDS",
    "GOAL_KEYWORDS",
    "EXT_LANG_MAP",
    "FENCE_LANG_MAP",
    "IntentAgent",
]
