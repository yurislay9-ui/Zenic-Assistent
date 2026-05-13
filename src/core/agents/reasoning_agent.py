"""
ZENIC-AGENTS - ReasoningAgent (Facade)

Thin facade — all logic lives in reasoning_agent_parts/.
"""

from .reasoning_agent_parts import *  # noqa: F401,F403
from .reasoning_agent_parts import ReasoningAgent, PROBLEM_TEMPLATES, PROBLEM_KEYWORDS

__all__ = [
    "MAX_REASONING_STEPS",
    "MIN_CONFIDENCE_ACCEPT",
    "PROBLEM_TEMPLATES",
    "PROBLEM_KEYWORDS",
    "ReasoningAgent",
]
