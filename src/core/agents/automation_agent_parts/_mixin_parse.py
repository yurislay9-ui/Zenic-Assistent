"""
Mixin: JSON and free-text parsing helpers for AutomationAgent.
"""

from typing import Any, Dict, List, Optional

from ._imports import AutomationOutput, TriggerSpec, ActionSpec, ScheduleSpec


class ParseMixin:
    """_json_to_automation_output and _parse_free_text_automation for AutomationAgent."""

    def _json_to_automation_output(self, data: Dict[str, Any],
                                    source: str = "llm") -> Optional[AutomationOutput]:
        """Convierte dict JSON a AutomationOutput."""
        name = str(data.get("name", "unnamed_automation")).strip()
        if not name:
            name = "unnamed_automation"

        # Parse triggers
        triggers = []
        for t in data.get("triggers", []):
            if isinstance(t, dict):
                triggers.append(TriggerSpec(
                    type=str(t.get("type", "manual")),
                    config=t.get("config", {}),
                    description=str(t.get("description", "")),
                ))

        # Parse actions
        actions = []
        for a in data.get("actions", []):
            if isinstance(a, dict):
                actions.append(ActionSpec(
                    type=str(a.get("type", "log")),
                    config=a.get("config", {}),
                    description=str(a.get("description", "")),
                ))

        # Parse schedule
        sched = data.get("schedule", {})
        if isinstance(sched, dict):
            schedule = ScheduleSpec(
                type=str(sched.get("type", "manual")),
                interval_seconds=int(sched.get("interval_seconds", 0)),
                cron_expression=str(sched.get("cron_expression", "")),
                description=str(sched.get("description", "")),
            )
        else:
            schedule = ScheduleSpec()

        # Parse conditions
        conditions = data.get("conditions", [])
        if isinstance(conditions, str):
            conditions = [conditions]

        description = str(data.get("description", ""))

        return AutomationOutput(
            name=name,
            triggers=triggers,
            actions=actions,
            schedule=schedule,
            conditions=conditions if isinstance(conditions, list) else [],
            description=description,
            source=source,
        )

    def _parse_free_text_automation(self, text: str,
                                     source: str = "llm") -> Optional[AutomationOutput]:
        """Parsea texto libre del LLM cuando no hay JSON."""
        if not text or len(text) < 10:
            return None

        # Extract name from first line
        lines = text.strip().split('\n')
        name = self._extract_name(lines[0])

        return AutomationOutput(
            name=name,
            triggers=[TriggerSpec(type="manual", description="Free-text trigger")],
            actions=[ActionSpec(type="log", config={"message": text[:200]},
                               description="Free-text action")],
            schedule=ScheduleSpec(type="manual"),
            description=text[:200],
            source=source,
        )
