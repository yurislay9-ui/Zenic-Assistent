"""
ZENIC-AGENTS - AutomationAgent (Facade)

Thin facade — all logic lives in automation_agent_parts/.
"""

from .automation_agent_parts import *  # noqa: F401,F403
from .automation_agent_parts import AutomationAgent, TRIGGER_KEYWORDS, ACTION_KEYWORDS

__all__ = [
    "TRIGGER_KEYWORDS",
    "ACTION_KEYWORDS",
    "SCHEDULE_PATTERNS",
    "AutomationAgent",
]
