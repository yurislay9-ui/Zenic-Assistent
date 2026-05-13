"""
Mixin: BaseAgent interface methods (build_prompt, parse_response).
"""

from typing import Any, Optional, Tuple

from ._imports import (
    IntentInput, IntentOutput, AgentPrompts, PromptBuilder,
)


class PromptMixin:
    """build_prompt and parse_response for IntentAgent."""

    def build_prompt(self, input_data: Any) -> Tuple[str, str]:
        """Construye system + user prompt para clasificación de intención."""
        if isinstance(input_data, IntentInput):
            message = input_data.message
            context = input_data.context
        elif isinstance(input_data, str):
            message = input_data
            context = ""
        else:
            message = str(input_data)
            context = ""

        system_prompt = AgentPrompts.INTENT_SYSTEM
        user_prompt = AgentPrompts.INTENT_USER.format(message=message[:500])

        if context:
            user_prompt = PromptBuilder.add_context_to_prompt(
                user_prompt, {"previous_context": context[:300]}
            )

        return system_prompt, user_prompt

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[IntentOutput]:
        """Parsea la respuesta del LLM a un IntentOutput válido."""
        # Limpiar texto del LLM (quitar think blocks, markdown)
        cleaned = self.clean_llm_text(raw_response)

        # Intentar extraer JSON
        json_data = self.extract_json(cleaned)
        if json_data and isinstance(json_data, dict):
            return self._json_to_intent_output(json_data, source="llm")

        # Si no hay JSON, intentar parsear texto libre
        return self._parse_free_text(cleaned, source="llm")
