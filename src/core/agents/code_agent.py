"""
Facade for CodeAgent — thin re-export shim.

The full implementation has been modularised into the
``code_agent_parts`` sub-package using the mixin pattern:

  - code_agent_parts.helpers   — static / utility methods + constants
  - code_agent_parts.scaffolds  — multi-language scaffold generators
  - code_agent_parts.fallbacks  — fallback generators + transformers
  - code_agent_parts.defensive  — criticality adjustments + defensive injection
  - code_agent_parts.core       — CodeAgent class (assembles all mixins)

All public symbols are still importable from this module exactly as before::

    from src.core.agents.code_agent import CodeAgent
"""

from src.core.agents.code_agent_parts.core import CodeAgent  # noqa: F401

__all__ = ["CodeAgent"]
