"""
A39 ConclusionExtractor — SINGLE RESPONSIBILITY: Extract the final conclusion from reasoning steps.

Deterministic pattern-based extraction. No AI.
Extracts the core conclusion from a sequence of reasoning steps
using bilingual conclusion markers, sentence analysis, and
strength estimation based on supporting evidence.

Ported from:
  - ReasoningEngine._extract_conclusion() (reasoning_parts/_helpers_mixin.py)
  - ReasoningEngine step accumulation logic (reasoning_parts/_step_mixin.py)
"""

from __future__ import annotations

import re
from typing import Any, Optional

from ..resilience import BaseAgent
from ..schemas import Conclusion, DecomposedSteps, ReasoningResult, ReasoningStep

# ──────────────────────────────────────────────────────────────
# CONCLUSION MARKERS — EN + ES bilingual
# ──────────────────────────────────────────────────────────────

# Markers that introduce a conclusion (ordered by specificity)
CONCLUSION_MARKERS_EN = [
    "therefore", "thus", "in conclusion", "conclusion:",
    "so,", "hence", "as a result", "consequently",
    "the answer is", "final answer", "in summary",
    "to summarize", "result:", "output:",
]
CONCLUSION_MARKERS_ES = [
    "por lo tanto", "en conclusión", "en conclusion",
    "resultado:", "así que", "por consiguiente",
    "como resultado", "en resumen", "para resumir",
    "la respuesta es", "respuesta final",
]

# All markers combined for matching
ALL_CONCLUSION_MARKERS = CONCLUSION_MARKERS_EN + CONCLUSION_MARKERS_ES

# Negative markers — NOT a conclusion
NEGATIVE_MARKERS = [
    "however", "but", "although", "on the other hand",
    "pero", "sin embargo", "aunque", "por otro lado",
]

# Maximum conclusion text length
MAX_CONCLUSION_LENGTH = 300


class ConclusionExtractor(BaseAgent[Conclusion]):
    """
    A39: Extract the final conclusion from reasoning steps.

    Single Responsibility: Conclusion extraction ONLY.
    Method: Pattern-based extraction with bilingual markers (deterministic).
    Fallback: Return last step's conclusion or empty string.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A39_ConclusionExtractor", **kwargs)

    def execute(self, input_data: Any) -> Conclusion:
        """
        Extract the final conclusion from reasoning steps.

        input_data can be:
          - ReasoningResult object (preferred — from A37)
          - DecomposedSteps object (from A36)
          - dict with 'result' key (ReasoningResult)
          - dict with 'steps' key (list of ReasoningStep)
          - list of ReasoningStep objects
          - str (raw text to extract conclusion from)
        """
        steps = self._extract_steps(input_data)
        answer = self._extract_answer(input_data)

        # Strategy 1: Extract from step conclusions
        if steps:
            return self._extract_from_steps(steps, answer)

        # Strategy 2: Extract from raw answer text
        if answer:
            return self._extract_from_text(answer)

        # No data available
        return Conclusion(
            text="",
            supported_by=[],
            strength=0.0,
            source="deterministic",
        )

    def _extract_steps(self, input_data: Any) -> list[ReasoningStep]:
        """Extract reasoning steps from input."""
        if isinstance(input_data, ReasoningResult):
            return input_data.steps
        elif isinstance(input_data, DecomposedSteps):
            return input_data.steps
        elif isinstance(input_data, list):
            if all(isinstance(s, ReasoningStep) for s in input_data):
                return input_data
        elif isinstance(input_data, dict):
            result = input_data.get("result")
            if isinstance(result, ReasoningResult):
                return result.steps
            steps = input_data.get("steps", [])
            if isinstance(steps, list):
                return steps
        return []

    def _extract_answer(self, input_data: Any) -> str:
        """Extract answer text from input."""
        if isinstance(input_data, str):
            return input_data
        elif isinstance(input_data, ReasoningResult):
            return input_data.answer
        elif isinstance(input_data, dict):
            return input_data.get("answer", input_data.get("text", ""))
        if hasattr(input_data, "answer"):
            return getattr(input_data, "answer", "")
        return ""

    def _extract_from_steps(
        self, steps: list[ReasoningStep], answer: str
    ) -> Conclusion:
        """
        Extract conclusion from reasoning steps.

        Strategy:
          1. Check the last step's conclusion (most likely to be final)
          2. Look for conclusion markers across all step conclusions
          3. Combine step conclusions into a coherent summary
        """
        # Collect all non-empty step conclusions
        step_conclusions = [
            s.conclusion for s in steps if s.conclusion
        ]

        if not step_conclusions:
            # Use step descriptions if no conclusions
            step_conclusions = [s.description for s in steps if s.description]

        if not step_conclusions:
            return Conclusion(
                text="",
                supported_by=[],
                strength=0.0,
                source="deterministic",
            )

        # Try to find a conclusion with explicit markers
        marked_conclusion = self._find_marked_conclusion(step_conclusions)
        if marked_conclusion:
            supporting = self._get_supporting_steps(steps, marked_conclusion)
            strength = self._estimate_strength(steps, marked_conclusion)
            return Conclusion(
                text=marked_conclusion[:MAX_CONCLUSION_LENGTH],
                supported_by=supporting,
                strength=strength,
                source="deterministic",
            )

        # Use the last step's conclusion as the final one
        final_conclusion = step_conclusions[-1]

        # If there's also an answer text, try to extract from it
        if answer:
            answer_conclusion = self._find_conclusion_in_text(answer)
            if answer_conclusion and len(answer_conclusion) > len(final_conclusion):
                final_conclusion = answer_conclusion

        supporting = self._get_supporting_steps(steps, final_conclusion)
        strength = self._estimate_strength(steps, final_conclusion)

        return Conclusion(
            text=final_conclusion[:MAX_CONCLUSION_LENGTH],
            supported_by=supporting,
            strength=strength,
            source="deterministic",
        )

    def _extract_from_text(self, text: str) -> Conclusion:
        """Extract conclusion from raw text (no steps available)."""
        conclusion = self._find_conclusion_in_text(text)

        if not conclusion:
            # Fallback: return the last meaningful sentence
            conclusion = self._last_meaningful_sentence(text)

        strength = 0.3 if conclusion else 0.0
        if conclusion:
            # Boost strength if conclusion markers are present
            text_lower = conclusion.lower()
            for marker in ALL_CONCLUSION_MARKERS:
                if marker in text_lower:
                    strength += 0.1
                    break

        return Conclusion(
            text=(conclusion or "")[:MAX_CONCLUSION_LENGTH],
            supported_by=["raw_text"],
            strength=min(strength, 0.95),
            source="deterministic",
        )

    def _find_marked_conclusion(self, conclusions: list[str]) -> Optional[str]:
        """Find a conclusion that has explicit conclusion markers."""
        for conclusion in reversed(conclusions):
            conclusion_lower = conclusion.lower()
            for marker in ALL_CONCLUSION_MARKERS:
                idx = conclusion_lower.find(marker)
                if idx >= 0:
                    # Extract text after the marker
                    extracted = conclusion[idx + len(marker):].strip()
                    if extracted:
                        return extracted
        return None

    def _find_conclusion_in_text(self, text: str) -> Optional[str]:
        """Find conclusion in raw text using markers."""
        text_lower = text.lower()

        # Try each marker
        best_match = None
        best_pos = len(text)

        for marker in ALL_CONCLUSION_MARKERS:
            idx = text_lower.find(marker)
            if idx >= 0 and idx < best_pos:
                best_pos = idx
                extracted = text[idx + len(marker):].strip()
                if extracted:
                    best_match = extracted

        return best_match

    def _last_meaningful_sentence(self, text: str) -> str:
        """Return the last meaningful sentence from text."""
        sentences = re.split(r'[.!?]\s', text)
        meaningful = [s.strip() for s in sentences if len(s.strip()) > 10]
        return meaningful[-1] if meaningful else text[:200]

    def _get_supporting_steps(
        self, steps: list[ReasoningStep], conclusion: str
    ) -> list[str]:
        """Get list of step descriptions that support the conclusion."""
        supporting: list[str] = []
        for step in steps:
            if step.conclusion and step.conclusion != conclusion:
                supporting.append(f"step_{step.step_number}: {step.conclusion[:80]}")
            elif step.description and not step.conclusion:
                supporting.append(f"step_{step.step_number}: {step.description[:80]}")
        # Cap at 10 supporting entries
        return supporting[:10]

    def _estimate_strength(
        self, steps: list[ReasoningStep], conclusion: str
    ) -> float:
        """
        Estimate the strength of a conclusion.

        Factors:
          - Number of supporting steps (more = stronger)
          - Average step confidence (higher = stronger)
          - Conclusion length (very short = weaker)
          - Presence of certainty vs hedging markers
        """
        if not conclusion:
            return 0.0

        strength = 0.3  # Base

        # More supporting steps = stronger
        total_steps = len(steps)
        if total_steps >= 3:
            strength += 0.15
        elif total_steps >= 2:
            strength += 0.10
        elif total_steps >= 1:
            strength += 0.05

        # Average step confidence
        steps_with_conf = [s for s in steps if s.confidence > 0]
        if steps_with_conf:
            avg_conf = sum(s.confidence for s in steps_with_conf) / len(steps_with_conf)
            strength += avg_conf * 0.2

        # Conclusion length
        if len(conclusion) > 20:
            strength += 0.05
        if len(conclusion) > 100:
            strength += 0.05

        # Certainty vs hedging
        conc_lower = conclusion.lower()
        for marker in ["certainly", "clearly", "definitely", "obviously",
                       "ciertamente", "claramente"]:
            if marker in conc_lower:
                strength += 0.05
                break

        for marker in ["maybe", "perhaps", "might", "could be",
                       "quizás", "tal vez", "puede que"]:
            if marker in conc_lower:
                strength -= 0.05
                break

        return round(max(0.05, min(0.95, strength)), 2)

    def extract_summary(self, input_data: Any) -> str:
        """
        Extract a short summary conclusion (just the text, no metadata).

        Convenience method for callers that only need the conclusion text.
        """
        result = self.execute(input_data)
        return result.text

    def fallback(self, input_data: Any) -> Conclusion:
        """Fallback: Return empty conclusion with zero strength."""
        return Conclusion(
            text="",
            supported_by=[],
            strength=0.0,
            source="fallback",
        )
