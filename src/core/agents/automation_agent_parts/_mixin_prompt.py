"""
Mixin: BaseAgent interface methods (build_prompt, parse_response).
"""

from typing import Any, Optional, Tuple

from ._imports import (
    AutomationInput, AutomationOutput, AgentPrompts, PromptBuilder,
)


class PromptMixin:
    """build_prompt and parse_response for AutomationAgent."""

    def build_prompt(self, input_data: Any) -> Tuple[str, str]:
        """Construye system + user prompt para automatización."""
        if isinstance(input_data, AutomationInput):
            description = input_data.description
            context = input_data.context
        else:
            description = str(input_data)
            context = {}

        system_prompt = AgentPrompts.AUTOMATION_SYSTEM
        user_prompt = AgentPrompts.AUTOMATION_USER.format(
            description=description[:500],
        )

        # Add context
        if context:
            user_prompt = PromptBuilder.add_context_to_prompt(
                user_prompt, context
            )

        return system_prompt, user_prompt

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[AutomationOutput]:
        """Parsea la respuesta del LLM a un AutomationOutput válido."""
        cleaned = self.clean_llm_text(raw_response)

        # Try JSON extraction first
        json_data = self.extract_json(cleaned)
        if json_data and isinstance(json_data, dict):
            return self._json_to_automation_output(json_data, source="llm")

        # Try free text parsing
        return self._parse_free_text_automation(cleaned, source="llm")
