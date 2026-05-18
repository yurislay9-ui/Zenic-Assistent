"""
Compatibility adapters: v1 API → v2 agents.

This module provides v1-compatible wrappers around v2 agents so the
orchestrator can use agents without rewriting its call sites.

Every adapter:
  - Delegates to v2 agents internally (execute/run)
  - Exposes the v1 high-level API (classify_with_runner, validate_with_runner, etc.)
  - Translates between v1 schemas (IntentOutput, ValidationOutput, etc.)
    and v2 schemas (IntentResult, SecurityResult, etc.)

Once all orchestrator call sites are migrated to call v2 agents directly,
this module can be deprecated and removed.
"""

from __future__ import annotations

# Re-export backward-compatible aliases
from ._types import VALID_OPERATIONS, VALID_GOALS, logger

# Re-export adapter classes
from ._adapter import (
    SurgicalAgentCompat,
    ReasoningAgentCompat,
    BusinessLogicAgentCompat,
)

# Re-export mapper classes
from ._mapper import (
    AutomationAgentCompat,
    ValidationAgentCompat,
)

# Re-export migration class
from ._migration import AgentRunnerCompat

__all__ = [
    "SurgicalAgentCompat",
    "ReasoningAgentCompat",
    "BusinessLogicAgentCompat",
    "AutomationAgentCompat",
    "ValidationAgentCompat",
    "AgentRunnerCompat",
    # Backward-compatible aliases
    "VALID_OPERATIONS",
    "VALID_GOALS",
    "logger",
]
