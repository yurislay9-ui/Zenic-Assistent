"""
ZENIC-AGENTS — Chain template type definitions, enums, and constants.

Shared data structures used across the chain_templates sub-package.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..chain_composer import ComposedChain

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Persistence paths
# ---------------------------------------------------------------------------

_DB_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "db")
_DB_PATH = os.path.join(_DB_DIR, "chain_templates.sqlite")

# ---------------------------------------------------------------------------
#  Enums
# ---------------------------------------------------------------------------


class TemplateCategory(str, Enum):
    """Categories for chain templates."""

    MONITOR_DETECT = "monitor_detect"
    INCIDENT_RESPONSE = "incident_response"
    NOTIFICATION_ESCALATE = "notification_escalate"
    DATA_PIPELINE = "data_pipeline"
    COMPLIANCE = "compliance"


# ---------------------------------------------------------------------------
#  Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TemplateVariable:
    """A variable placeholder in a template."""

    name: str
    var_type: str = "str"  # str, int, float, bool, list
    default_value: Any = None
    required: bool = True
    description: str = ""


@dataclass
class TemplateStep:
    """A single step within a chain template."""

    step_type: str  # trigger, condition, action, notification, delay, sub_chain
    config_template: dict[str, Any] = field(default_factory=dict)
    next_step_id: str = ""
    condition_expr: str = ""
    timeout_ms: int = 30000


@dataclass
class ChainTemplate:
    """A reusable workflow template with variable placeholders."""

    template_id: str = ""
    name: str = ""
    description: str = ""
    category: str = TemplateCategory.MONITOR_DETECT.value
    event_patterns: list[str] = field(default_factory=list)
    intent_keywords: list[str] = field(default_factory=list)
    steps: list[TemplateStep] = field(default_factory=list)
    variables: list[TemplateVariable] = field(default_factory=list)
    version: str = "1.0.0"
    created_at: float = 0.0


# ---------------------------------------------------------------------------
#  Variable substitution
# ---------------------------------------------------------------------------


def _substitute_value(value: Any, variables: dict[str, Any]) -> Any:
    """Recursively substitute {{variable}} placeholders in a value."""
    if isinstance(value, str):
        # Check if the entire string is a single placeholder
        if value.startswith("{{") and value.endswith("}}") and value.count("{{") == 1:
            var_name = value[2:-2].strip()
            if var_name in variables:
                return variables[var_name]
            return value
        # Substitute multiple placeholders within a string
        result = value
        for var_name, var_value in variables.items():
            placeholder = "{{" + var_name + "}}"
            if placeholder in result:
                result = result.replace(placeholder, str(var_value))
        return result
    if isinstance(value, dict):
        return {k: _substitute_value(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_value(item, variables) for item in value]
    return value
