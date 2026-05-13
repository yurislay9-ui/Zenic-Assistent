"""
Mixin: BaseAgent interface methods (build_prompt, parse_response).
"""

from typing import Any, Optional, Tuple

from ._imports import (
    ReasoningInput, ReasoningOutput, AgentPrompts, PromptBuilder, logger,
)


class PromptMixin:
    """build_prompt and parse_response for ReasoningAgent."""

    def build_prompt(self, input_data: Any) -> Tuple[str, str]:
        """Construye system + user prompt según el modo de razonamiento."""
        if isinstance(input_data, ReasoningInput):
            query = input_data.query
            mode = input_data.mode
            context = input_data.context
        elif isinstance(input_data, str):
            query = input_data
            mode = "step_by_step"
            context = ""
        else:
            query = str(input_data)
            mode = "step_by_step"
            context = ""

        # Select system prompt based on mode
        mode_prompts = {
            "step_by_step": AgentPrompts.REASONING_SYSTEM_STEP_BY_STEP,
            "self_reflect": AgentPrompts.REASONING_SYSTEM_SELF_REFLECT,
            "with_context": AgentPrompts.REASONING_SYSTEM_WITH_CONTEXT,
        }
        system_prompt = mode_prompts.get(mode, AgentPrompts.REASONING_SYSTEM_STEP_BY_STEP)

        # Build user prompt
        user_prompt = AgentPrompts.REASONING_USER.format(query=query[:500])

        # Inject context if available
        if context:
            user_prompt = PromptBuilder.add_context_to_prompt(
                user_prompt, {"additional_context": context[:300]}
            )

        # Inject memory context if available
        mem_ctx = self._get_memory_context(query)
        if mem_ctx:
            user_prompt = PromptBuilder.add_context_to_prompt(
                user_prompt, {"relevant_experience": mem_ctx[:300]}
            )

        return system_prompt, user_prompt

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[ReasoningOutput]:
        """Parsea la respuesta del LLM a un ReasoningOutput válido."""
        cleaned = self.clean_llm_text(raw_response)

        # Try JSON extraction first
        json_data = self.extract_json(cleaned)
        if json_data and isinstance(json_data, dict):
            return self._json_to_reasoning_output(json_data, source="llm")

        # Try to extract structured answer from text
        return self._parse_free_text_reasoning(cleaned, source="llm")
