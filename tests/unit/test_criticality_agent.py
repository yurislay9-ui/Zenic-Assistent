"""
Unit tests for CriticalityAgent (F4).

Tests the agent that unifies criticality routing:
  - normalize_criticality() (type mismatch resolution)
  - level_to_path() (DAG path mapping)
  - Keyword signal analysis
  - Operation/Goal baseline signal
  - History signal
  - Confidence computation
  - Fallback multi-signal fusion
  - LLM response parsing
  - assess_deterministic() direct API
  - assess_with_runner() AgentRunner integration
  - Elevation rules (MacroRouter signal)
"""

from .test_criticality_parts import *  # noqa: F401,F403
from .test_criticality_parts import __all__  # noqa: F401
from .test_criticality_parts.conftest import *  # noqa: F401,F403
