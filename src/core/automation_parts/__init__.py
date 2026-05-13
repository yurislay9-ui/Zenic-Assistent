"""
automation_parts — Sub-modules for AutomationEngine.

Re-exports all public symbols for convenient access.
"""

from .types import (
    DB_DIR,
    DB_PATH,
    PROJECTS_DIR,
    TriggerType,
    ActionType,
    Trigger,
    Action,
    Workflow,
    WorkflowExecution,
)
from .engine import AutomationEngine

__all__ = [
    # Constants
    "DB_DIR",
    "DB_PATH",
    "PROJECTS_DIR",
    # Enums
    "TriggerType",
    "ActionType",
    # Dataclasses
    "Trigger",
    "Action",
    "Workflow",
    "WorkflowExecution",
    # Main class
    "AutomationEngine",
]
