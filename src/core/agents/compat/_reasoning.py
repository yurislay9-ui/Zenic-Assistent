"""
compat._reasoning — ReasoningAgentCompat v1→v2 wrapper.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.agents.reasoning import TemplateReasoner
from src.core.agents.schemas import ReasoningResult
from src.core.agents.schemas._v1_compat_schemas import ReasoningOutput, ReasoningStep as V1ReasoningStep

logger = logging.getLogger(__name__)


class ReasoningAgentCompat:
    """v1-compatible ReasoningAgent wrapper around v2 TemplateReasoner."""

    def __init__(self, semantic_engine=None, smart_memory=None, **kwargs) -> None:
        self._semantic = semantic_engine
        self._memory = smart_memory
        self._reasoner = TemplateReasoner(**kwargs)
        self._call_count = 0

    def reason_with_runner(self, runner: Any, query: str,
                           mode: str = "step_by_step",
                           context: str = "") -> ReasoningOutput:
        """Reason using v2 TemplateReasoner."""
        self._call_count += 1

        input_data = {"query": query, "context": context, "mode": mode}
        result = self._reasoner.run(input_data)

        data = result.get("data")
        if isinstance(data, ReasoningResult):
            return ReasoningOutput(
                answer=data.answer,
                confidence=data.confidence,
                mode=mode,
                steps=[
                    V1ReasoningStep(
                        step_number=s.step_number,
                        description=s.description,
                        conclusion=s.conclusion,
                    )
                    for s in data.steps
                ],
                refinements=0,
                context_used=[context] if context else [],
                memory_hits=0,
                source=data.source,
                total_duration_ms=int(result.get("duration_ms", 0)),
            )

        return ReasoningOutput(
            answer="Unable to reason about this query",
            confidence=0.1, mode=mode, source="fallback",
        )

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "name": "ReasoningAgentCompat",
            "call_count": self._call_count,
            "reasoner": self._reasoner.stats,
        }
