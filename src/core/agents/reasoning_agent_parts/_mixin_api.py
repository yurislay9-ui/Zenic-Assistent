"""
Mixin: High-level API methods (reason, reason_with_runner, to_reasoning_result).
"""

from typing import Any

from ._imports import ReasoningInput, ReasoningOutput, AgentResult


class ApiMixin:
    """High-level API and conversion methods for ReasoningAgent."""

    def to_reasoning_result(self, output: ReasoningOutput) -> Any:
        """
        Convierte ReasoningOutput a ReasoningResult para compatibilidad
        con el pipeline existente (Phase 8 API).
        """
        from src.core.reasoning_engine import ReasoningMode, ReasoningResult, ReasoningStep as REStep

        mode_map = {
            "step_by_step": ReasoningMode.STEP_BY_STEP,
            "self_reflect": ReasoningMode.SELF_REFLECT,
            "with_context": ReasoningMode.WITH_CONTEXT,
        }
        mode = mode_map.get(output.mode, ReasoningMode.FALLBACK)

        # Convert steps
        converted_steps = []
        for s in output.steps:
            converted_steps.append(REStep(
                step_number=s.step_number,
                thought=s.description,
                conclusion=s.conclusion,
                confidence=getattr(output, 'confidence', 0.5) if output.confidence is not None else 0.5,
                source=output.source,
            ))

        return ReasoningResult(
            answer=output.answer,
            confidence=output.confidence,
            mode=mode,
            steps=converted_steps,
            total_duration_ms=output.total_duration_ms,
            refinements=output.refinements,
            context_used=bool(output.context_used),
            memory_hits=output.memory_hits,
            source=output.source,
        )

    def reason(self, query: str, mode: str = "step_by_step",
               context: str = "", max_steps: int = 3) -> ReasoningOutput:
        """
        Método principal de razonamiento (sin AgentRunner).

        Para razonamiento con LLM, usar:
            output = agent.classify_with_runner(runner, query, mode, context)
        """
        input_data = ReasoningInput(
            query=query, mode=mode, context=context, max_steps=max_steps
        )
        return self.fallback(input_data)

    def reason_with_runner(self, runner: Any, query: str,
                           mode: str = "step_by_step",
                           context: str = "",
                           max_steps: int = 3) -> ReasoningOutput:
        """Razona usando AgentRunner (LLM → fallback)."""
        input_data = ReasoningInput(
            query=query, mode=mode, context=context, max_steps=max_steps
        )
        result: AgentResult = runner.run(self, input_data)

        if result.success and isinstance(result.data, ReasoningOutput):
            return result.data

        return self.fallback(input_data)
