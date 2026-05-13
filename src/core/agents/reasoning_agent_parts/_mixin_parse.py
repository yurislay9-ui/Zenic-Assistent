"""
Mixin: JSON/text parsing helpers for ReasoningAgent.
"""

from typing import Any, Dict, List, Optional

from ._imports import ReasoningOutput, ReasoningStep


class ParseMixin:
    """_json_to_reasoning_output and _parse_free_text_reasoning for ReasoningAgent."""

    def _json_to_reasoning_output(self, data: Dict[str, Any],
                                  source: str = "llm") -> Optional[ReasoningOutput]:
        """Convierte un dict JSON a ReasoningOutput."""
        answer = str(data.get("answer", "")).strip()
        if not answer:
            return None

        confidence = data.get("confidence", 0.5)
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.5

        # Parse steps
        steps = []
        raw_steps = data.get("steps", [])
        if isinstance(raw_steps, list):
            for i, s in enumerate(raw_steps):
                if isinstance(s, dict):
                    steps.append(ReasoningStep(
                        step_number=s.get("step_number", i + 1),
                        description=s.get("description", ""),
                        conclusion=s.get("conclusion", ""),
                    ))

        refinements = data.get("refinements", 0)
        try:
            refinements = int(refinements)
        except (ValueError, TypeError):
            refinements = 0

        context_used = data.get("context_used", [])
        if isinstance(context_used, str):
            context_used = [context_used]

        return ReasoningOutput(
            answer=answer,
            confidence=confidence,
            mode="step_by_step",
            steps=steps,
            refinements=refinements,
            context_used=context_used if isinstance(context_used, list) else [],
            memory_hits=0,
            source=source,
        )

    def _parse_free_text_reasoning(self, text: str,
                                   source: str = "llm") -> Optional[ReasoningOutput]:
        """Parsea texto libre del LLM cuando no hay JSON."""
        if not text or len(text) < 10:
            return None

        # Extract conclusion markers
        conclusion = text
        markers = ["therefore", "thus", "conclusion:", "so,", "hence",
                    "por lo tanto", "en conclusión", "resultado:"]
        text_lower = text.lower()
        for marker in markers:
            idx = text_lower.find(marker)
            if idx >= 0:
                conclusion = text[idx + len(marker):].strip()[:300]
                break

        # Estimate confidence from text
        confidence = 0.5
        certainty = ["certainly", "clearly", "definitely", "obviously"]
        hedging = ["maybe", "perhaps", "might", "could be", "possibly"]
        if any(m in text_lower for m in certainty):
            confidence += 0.1
        if any(m in text_lower for m in hedging):
            confidence -= 0.1

        return ReasoningOutput(
            answer=text[:500],
            confidence=max(0.1, min(0.9, confidence)),
            mode="step_by_step",
            steps=[ReasoningStep(
                step_number=1,
                description="Free-text reasoning from LLM",
                conclusion=conclusion[:300],
            )],
            source=source,
        )
