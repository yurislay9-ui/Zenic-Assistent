"""
compat._automation — AutomationAgentCompat v1→v2 wrapper.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.agents.automation import (
    TriggerInferrer, ActionInferrer, ScheduleParser,
    AutomationNamer, WorkflowSerializer,
)
from src.core.agents.schemas._v1_compat_schemas import AutomationOutput
from src.core.shared.agent_schemas import (
    TriggerSpec as SharedTriggerSpec,
    ActionSpec as SharedActionSpec,
    ScheduleSpec as SharedScheduleSpec,
)

logger = logging.getLogger(__name__)


class AutomationAgentCompat:
    """v1-compatible AutomationAgent wrapper around v2 automation agents."""

    def __init__(self, semantic_engine=None, smart_memory=None, **kwargs) -> None:
        self._semantic = semantic_engine
        self._memory = smart_memory
        self._trigger_inferrer = TriggerInferrer(**kwargs)
        self._action_inferrer = ActionInferrer(**kwargs)
        self._schedule_parser = ScheduleParser(**kwargs)
        self._namer = AutomationNamer(**kwargs)
        self._serializer = WorkflowSerializer(**kwargs)
        self._call_count = 0

    def design_with_runner(self, runner: Any, description: str,
                           **kwargs) -> AutomationOutput:
        """Design automation using v2 agents."""
        self._call_count += 1

        trigger_result = self._trigger_inferrer.run(description)
        action_result = self._action_inferrer.run(description)
        schedule_result = self._schedule_parser.run(description)
        name_result = self._namer.run(description)

        triggers = self._extract_triggers(trigger_result)
        actions = self._extract_actions(action_result)
        schedule = self._extract_schedule(schedule_result)
        name = self._extract_name(name_result)

        return AutomationOutput(
            name=name, triggers=triggers, actions=actions,
            schedule=schedule, conditions=[],
            description=description[:200], source="deterministic",
        )

    def to_workflow_dict(self, output: AutomationOutput) -> dict:
        """Convert AutomationOutput to workflow dict."""
        return {
            "name": output.name,
            "triggers": [
                {"type": t.type, "config": t.config, "description": t.description}
                for t in output.triggers
            ],
            "actions": [
                {"type": a.type, "config": a.config, "description": a.description}
                for a in output.actions
            ],
            "schedule": {
                "type": output.schedule.type,
                "cron": output.schedule.cron_expression,
            },
            "source": output.source,
        }

    def _extract_triggers(self, result: dict) -> list[SharedTriggerSpec]:
        data = result.get("data")
        if isinstance(data, dict) and "triggers" in data:
            raw = data["triggers"]
            if isinstance(raw, list):
                return [
                    t if isinstance(t, SharedTriggerSpec) else SharedTriggerSpec(
                        type=t.get("type", "manual") if isinstance(t, dict) else "manual",
                        config=t.get("config", {}) if isinstance(t, dict) else {},
                        description=t.get("description", "") if isinstance(t, dict) else str(t),
                    )
                    for t in raw
                ]
        return [SharedTriggerSpec(type="manual", description="Inferred from user description")]

    def _extract_actions(self, result: dict) -> list[SharedActionSpec]:
        data = result.get("data")
        if isinstance(data, dict) and "actions" in data:
            raw = data["actions"]
            if isinstance(raw, list):
                return [
                    a if isinstance(a, SharedActionSpec) else SharedActionSpec(
                        type=a.get("type", "log") if isinstance(a, dict) else "log",
                        config=a.get("config", {}) if isinstance(a, dict) else {},
                        description=a.get("description", "") if isinstance(a, dict) else str(a),
                    )
                    for a in raw
                ]
        return [SharedActionSpec(type="log", description="Default log action")]

    def _extract_schedule(self, result: dict) -> SharedScheduleSpec:
        data = result.get("data")
        if isinstance(data, dict):
            return SharedScheduleSpec(
                type=data.get("type", "manual"),
                cron=data.get("cron", ""),
                interval_seconds=data.get("interval_seconds", 0),
                description=data.get("description", ""),
            )
        return SharedScheduleSpec()

    def _extract_name(self, result: dict) -> str:
        data = result.get("data")
        if isinstance(data, dict):
            return data.get("name", data.get("slug", "unnamed_automation"))
        if isinstance(data, str):
            return data
        return "unnamed_automation"

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "name": "AutomationAgentCompat",
            "call_count": self._call_count,
        }
