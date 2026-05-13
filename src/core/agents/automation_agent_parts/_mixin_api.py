"""
Mixin: High-level API and compatibility methods for AutomationAgent.
"""

from typing import Any, Dict, Optional

from ._imports import AutomationInput, AutomationOutput, AgentResult


class ApiMixin:
    """High-level API: design_with_runner and to_workflow_dict for AutomationAgent."""

    def design_with_runner(self, runner: Any, description: str,
                           context: Optional[Dict[str, Any]] = None) -> AutomationOutput:
        """Diseña automatización usando AgentRunner (LLM → fallback)."""
        input_data = AutomationInput(
            description=description,
            context=context or {},
        )
        result: AgentResult = runner.run(self, input_data)
        if result.success and isinstance(result.data, AutomationOutput):
            return result.data
        return self.fallback(input_data)

    def to_workflow_dict(self, output: AutomationOutput) -> Dict[str, Any]:
        """
        Convierte AutomationOutput a formato compatible con
        AutomationEngine.Workflow para integración legacy.
        """
        return {
            "name": output.name,
            "description": output.description,
            "trigger": {
                "type": output.triggers[0].type if output.triggers else "schedule",
                "config": output.triggers[0].config if output.triggers else {},
            },
            "actions": [
                {"type": a.type, "config": a.config, "description": a.description}
                for a in output.actions
            ],
            "schedule": {
                "type": output.schedule.type,
                "interval_seconds": output.schedule.interval_seconds,
                "cron_expression": output.schedule.cron_expression,
            },
            "conditions": output.conditions,
        }
