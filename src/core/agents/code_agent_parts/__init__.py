"""
code_agent_parts — modularised CodeAgent components.

Re-exports the assembled CodeAgent class and shared constants so that
downstream code can import exactly as before::

    from src.core.agents.code_agent_parts import CodeAgent
    from src.core.agents.code_agent_parts import LANG_EXTENSIONS, TASK_PROMPTS
"""

from src.core.agents.code_agent_parts.core import CodeAgent
from src.core.agents.code_agent_parts.helpers import LANG_EXTENSIONS, TASK_PROMPTS
from src.core.agents.code_agent_parts.helpers import CodeAgentHelpersMixin
from src.core.agents.code_agent_parts.scaffolds import CodeAgentScaffoldsMixin
from src.core.agents.code_agent_parts.fallbacks import CodeAgentFallbacksMixin
from src.core.agents.code_agent_parts.defensive import CodeAgentDefensiveMixin

__all__ = [
    "CodeAgent",
    "LANG_EXTENSIONS",
    "TASK_PROMPTS",
    "CodeAgentHelpersMixin",
    "CodeAgentScaffoldsMixin",
    "CodeAgentFallbacksMixin",
    "CodeAgentDefensiveMixin",
]
