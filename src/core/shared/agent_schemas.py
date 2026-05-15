"""Shared agent schemas — single source of truth for types used across the agent system.

These types are shared across the unified agents/ module (formerly agents/ v1
and agents_v2/ v2, now merged). This module is the canonical location for
cross-cutting schema types:

    agents/  →  shared/agent_schemas  ←  agents/

E-13 FIX: Moved from agents/schemas/types/_advanced_types.py to
eliminate the v1->v2 dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationIssue:
    """A single validation finding.

    Used by both compat ValidationAgent and validation chain agents.
    """
    severity: str = "warning"  # error|warning|info
    code: str = ""
    message: str = ""
    line: int = 0
    suggestion: str = ""


@dataclass
class TriggerSpec:
    """Trigger specification for automation agents.

    Used by both compat AutomationAgent and automation subsystem.
    """
    type: str = "manual"  # manual|schedule|event|webhook
    config: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    source: str = "deterministic"


@dataclass
class ActionSpec:
    """Action specification for automation agents.

    Used by both compat AutomationAgent and automation subsystem.
    """
    type: str = "log"  # email|http|db|file|webhook|notification|transform|schedule|log
    config: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    source: str = "deterministic"


class ScheduleSpec:
    """Schedule specification for automation agents.

    Used by both compat AutomationAgent and automation subsystem.

    Note: This class uses a manual __init__ instead of @dataclass because
    it supports a backward-compatible ``cron_expression`` alias parameter.
    The class-level attributes serve as documentation only; they are NOT
    dataclass fields and are overwritten by __init__.
    """

    # Instance attributes (set by __init__, documented here for IDE support)
    type: str          # manual|interval|cron|once
    cron: str
    interval_seconds: int
    description: str
    source: str

    def __init__(self, type: str = "manual", cron: str = "",
                 interval_seconds: int = 0, description: str = "",
                 source: str = "deterministic",
                 cron_expression: str = "") -> None:
        """Allow both ``cron`` and ``cron_expression`` for backward compatibility."""
        self.type = type
        self.cron = cron or cron_expression  # cron_expression is an alias
        self.interval_seconds = interval_seconds
        self.description = description
        self.source = source

    @property
    def cron_expression(self) -> str:
        """Backward-compatible alias for ``cron`` (legacy used ``cron_expression``)."""
        return self.cron
