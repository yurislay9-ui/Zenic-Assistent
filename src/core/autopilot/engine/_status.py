"""ZENIC-AGENTS - Autopilot Engine: Status Enum"""

from __future__ import annotations

from enum import Enum


class AutopilotStatus(str, Enum):
    """Status of the autopilot engine for a specific objective."""

    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
