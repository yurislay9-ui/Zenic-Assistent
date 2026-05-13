"""
A34 WorkflowSerializer — SINGLE RESPONSIBILITY: Serialize automation into executable workflow spec.

Deterministic. No AI.
Takes TriggerSpec + ActionSpec + ScheduleSpec + Conditions and produces
a complete WorkflowSpec with YAML, JSON, and executable dict formats.
"""

from __future__ import annotations

import json
from typing import Any

from ..resilience import BaseAgent
from ..schemas import (
    TriggerSpec,
    ActionSpec,
    ScheduleSpec,
    ConditionResult,
    WorkflowSpec,
)

# ──────────────────────────────────────────────────────────────
# WORKFLOW TEMPLATE — Base structure for serialized workflows
# ──────────────────────────────────────────────────────────────

WORKFLOW_VERSION = "1.0"


class WorkflowSerializer(BaseAgent[WorkflowSpec]):
    """
    A34: Serialize automation into executable workflow spec.

    Single Responsibility: Workflow serialization ONLY.
    Method: Template composition + structured serialization (deterministic).
    Fallback: Return minimal empty workflow.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A34_WorkflowSerializer", **kwargs)

    def execute(self, input_data: Any) -> WorkflowSpec:
        """
        Serialize automation components into a workflow spec.

        input_data should be a dict with:
          - 'trigger': TriggerSpec or dict
          - 'actions': List[ActionSpec] or list of dicts
          - 'schedule': ScheduleSpec or dict (optional)
          - 'conditions': ConditionResult or list of str (optional)
          - 'name': str (optional)
          - 'description': str (optional)
        """
        if not isinstance(input_data, dict):
            return self.fallback(input_data)

        # Extract components
        trigger = self._normalize_trigger(input_data.get("trigger"))
        actions = self._normalize_actions(input_data.get("actions"))
        schedule = self._normalize_schedule(input_data.get("schedule"))
        conditions = self._normalize_conditions(input_data.get("conditions"))
        name = input_data.get("name", "unnamed_workflow")
        description = input_data.get("description", "")

        # Build executable dict
        executable = self._build_executable(
            name, description, trigger, actions, schedule, conditions
        )

        # Generate YAML representation
        yaml_str = self._to_yaml(executable)

        # Generate JSON representation
        json_str = json.dumps(executable, indent=2, ensure_ascii=False)

        return WorkflowSpec(
            yaml=yaml_str,
            json_spec=json_str,
            executable=executable,
            source="deterministic",
        )

    def _normalize_trigger(self, trigger: Any) -> dict[str, Any]:
        """Normalize trigger to dict format."""
        if isinstance(trigger, TriggerSpec):
            return {
                "type": trigger.type,
                "config": trigger.config,
                "description": trigger.description,
            }
        elif isinstance(trigger, dict):
            return trigger
        return {"type": "manual", "config": {}}

    def _normalize_actions(self, actions: Any) -> list[dict[str, Any]]:
        """Normalize actions to list of dicts."""
        if not actions:
            return [{"type": "log", "config": {"message": "No action specified"}}]

        normalized = []
        if isinstance(actions, list):
            for action in actions:
                if isinstance(action, ActionSpec):
                    normalized.append({
                        "type": action.type,
                        "config": action.config,
                        "description": action.description,
                    })
                elif isinstance(action, dict):
                    normalized.append(action)
        elif isinstance(actions, ActionSpec):
            normalized.append({
                "type": actions.type,
                "config": actions.config,
                "description": actions.description,
            })
        return normalized

    def _normalize_schedule(self, schedule: Any) -> dict[str, Any]:
        """Normalize schedule to dict format."""
        if isinstance(schedule, ScheduleSpec):
            return {
                "type": schedule.type,
                "cron": schedule.cron,
                "interval_seconds": schedule.interval_seconds,
                "description": schedule.description,
            }
        elif isinstance(schedule, dict):
            return schedule
        return {"type": "manual"}

    def _normalize_conditions(self, conditions: Any) -> list[str]:
        """Normalize conditions to list of strings."""
        if isinstance(conditions, ConditionResult):
            return conditions.conditions
        elif isinstance(conditions, list):
            result = []
            for c in conditions:
                if isinstance(c, str):
                    result.append(c)
                elif isinstance(c, dict):
                    result.append(json.dumps(c))
            return result
        return []

    def _build_executable(
        self,
        name: str,
        description: str,
        trigger: dict[str, Any],
        actions: list[dict[str, Any]],
        schedule: dict[str, Any],
        conditions: list[str],
    ) -> dict[str, Any]:
        """Build the complete executable workflow dict."""
        workflow = {
            "version": WORKFLOW_VERSION,
            "name": name,
            "description": description,
            "trigger": trigger,
            "actions": actions,
            "schedule": schedule,
        }

        if conditions:
            workflow["conditions"] = conditions
            # Add logic tree if conditions present
            workflow["condition_operator"] = "AND"

        # Add metadata
        workflow["metadata"] = {
            "format_version": WORKFLOW_VERSION,
            "engine": "zenic_agents_v18",
            "deterministic": True,
        }

        return workflow

    def _to_yaml(self, data: dict[str, Any]) -> str:
        """Convert dict to YAML string (manual, no yaml dependency required)."""
        lines = []
        self._dict_to_yaml_lines(data, lines, indent=0)
        return "\n".join(lines)

    def _dict_to_yaml_lines(
        self, data: Any, lines: list[str], indent: int
    ) -> None:
        """Recursively convert dict to YAML lines."""
        prefix = "  " * indent

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    lines.append(f"{prefix}{key}:")
                    self._dict_to_yaml_lines(value, lines, indent + 1)
                elif isinstance(value, str):
                    # Quote strings with special chars
                    if any(c in value for c in ":{}[],'\"&*?|>!%@`#"):
                        lines.append(f'{prefix}{key}: "{value}"')
                    else:
                        lines.append(f"{prefix}{key}: {value}")
                elif isinstance(value, bool):
                    lines.append(f"{prefix}{key}: {'true' if value else 'false'}")
                elif value is None:
                    lines.append(f"{prefix}{key}: null")
                else:
                    lines.append(f"{prefix}{key}: {value}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    lines.append(f"{prefix}-")
                    self._dict_to_yaml_lines(item, lines, indent + 1)
                elif isinstance(item, str):
                    lines.append(f"{prefix}- {item}")
                else:
                    lines.append(f"{prefix}- {item}")

    def fallback(self, input_data: Any) -> WorkflowSpec:
        """Fallback: Return minimal empty workflow."""
        empty = {
            "version": WORKFLOW_VERSION,
            "name": "empty_workflow",
            "trigger": {"type": "manual"},
            "actions": [],
            "schedule": {"type": "manual"},
        }
        return WorkflowSpec(
            yaml=self._to_yaml(empty),
            json_spec=json.dumps(empty, indent=2),
            executable=empty,
            source="fallback",
        )
