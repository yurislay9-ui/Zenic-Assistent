"""
ZENIC-AGENTS - AutomationEngine (Workflow Automation for PYMEs)

Thin facade — all implementation lives in automation_parts sub-package.
"""

from .automation_parts import (
    DB_DIR,
    DB_PATH,
    PROJECTS_DIR,
    TriggerType,
    ActionType,
    Trigger,
    Action,
    Workflow,
    WorkflowExecution,
    AutomationEngine,
)

__all__ = [
    "DB_DIR",
    "DB_PATH",
    "PROJECTS_DIR",
    "TriggerType",
    "ActionType",
    "Trigger",
    "Action",
    "Workflow",
    "WorkflowExecution",
    "AutomationEngine",
]
