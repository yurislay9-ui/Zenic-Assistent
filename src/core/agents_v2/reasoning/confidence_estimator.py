"""
A38 ConfidenceEstimator — SINGLE RESPONSIBILITY: Estimate confidence in a reasoning result.

Deterministic statistical + heuristic estimation. No AI.
Evaluates multiple factors (result quality, evidence alignment,
template match, step completeness) to produce a confidence score
and a recommendation (proceed/caution/reject).

Ported from:
  - ReasoningEngine._estimate_confidence() (reasoning_parts/_helpers_mixin.py)
  - ReasoningEngine._fallback_evaluate() (reasoning_parts/_helpers_mixin.py)
  - ReasoningEngine._estimate_complexity() (reasoning_parts/_helpers_mixin.py)
"""

from __future__ import annotations

import re
from typing import Any, Optional

from ..resilience import BaseAgent
from ..schemas import ConfidenceResult, ReasoningResult, ReasoningStep

# ──────────────────────────────────────────────────────────────
# CONFIDENCE SCORING RULES
# ──────────────────────────────────────────────────────────────

# Certainty markers increase confidence
CERTAINTY_MARKERS_EN = [
    "certainly", "clearly", "definitely", "obviously", "surely",
    "without doubt", "undoubtedly", "absolutely", "guaranteed",
]
CERTAINTY_MARKERS_ES = [
    "ciertamente", "claramente", "definitivamente", "obviamente",
    "seguramente", "sin duda", "indudablemente", "absolutamente",
]

# Hedging markers decrease confidence
HEDGING_MARKERS_EN = [
    "maybe", "perhaps", "might", "could be", "possibly",
    "it seems", "likely", "probably", "i think", "might not",
]
HEDGING_MARKERS_ES = [
    "quizás", "tal vez", "puede que", "posiblemente",
    "parece que", "probablemente", "creo que", "a lo mejor",
]

# Security risk patterns significantly decrease confidence
SECURITY_RISK_PATTERNS = [
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\bos\.system\s*\(",
    r"\bsubprocess\.call\s*\([^)]*shell\s*=\s*True",
    r"\bpickle\.loads?\s*\(",
    r"\b__import__\s*\(",
]

# Quality issues that decrease confidence
QUALITY_ISSUES = [
    "TODO", "FIXME", "HACK", "XXX", "NOQA",
    "placeholder", "stub", "not implemented",
]

# Thresholds for recommendation levels
THRESHOLD_PROCEED = 0.7
THRESHOLD_CAUTION = 0.4
# Below THRESHOLD_CAUTION → reject


class ConfidenceEstimator(BaseAgent[ConfidenceResult]):
    """
    A38: Estimate confidence in a reasoning result.

    Single Responsibility: Confidence estimation ONLY.
    Method: Multi-factor heuristic scoring (deterministic).
    Fallback: Return low confidence with caution recommendation.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A38_ConfidenceEstimator", **kwargs)

    def execute(self, input_data: Any) -> ConfidenceResult:
        """
        Estimate confidence in a reasoning result.

        input_data can be:
          - ReasoningResult object (preferred)
          - dict with 'result' key (ReasoningResult or str)
          - dict with 'answer' and 'confidence' keys
          - str (raw text to evaluate)
        """
        result = self._extract_result(input_data)
        answer = self._extract_answer(input_data)
        base_confidence = self._extract_base_confidence(input_data)

        factors: list[str] = []

        # Factor 1: Answer length and detail
        length_score = self._score_answer_length(answer, factors)

        # Factor 2: Certainty vs hedging language
        language_score = self._score_language_certainty(answer, factors)

        # Factor 3: Security risk detection
        security_score = self._score_security_risks(answer, factors)

        # Factor 4: Quality issues
        quality_score = self._score_quality(answer, factors)

        # Factor 5: Step completeness (if ReasoningResult with steps)
        step_score = self._score_step_completeness(result, factors)

        # Factor 6: Template match bonus
        template_score = self._score_template_match(result, factors)

        # Compute weighted aggregate
        weights = {
            "length": 0.10,
            "language": 0.15,
            "security": 0.30,  # Security has highest weight
            "quality": 0.15,
            "steps": 0.15,
            "template": 0.15,
        }
        scores = {
            "length": length_score,
            "language": language_score,
            "security": security_score,
            "quality": quality_score,
            "steps": step_score,
            "template": template_score,
        }

        aggregate = base_confidence
        for factor_name, weight in weights.items():
            aggregate += (scores[factor_name] - 0.5) * weight * 2

        # Clamp to [0.05, 0.95]
        final_score = max(0.05, min(0.95, round(aggregate, 2)))

        # Determine recommendation
        if final_score >= THRESHOLD_PROCEED:
            recommendation = "proceed"
        elif final_score >= THRESHOLD_CAUTION:
            recommendation = "caution"
        else:
            recommendation = "reject"

        return ConfidenceResult(
            score=final_score,
            factors=factors,
            recommendation=recommendation,
            source="deterministic",
        )

    def _extract_result(self, input_data: Any) -> Optional[ReasoningResult]:
        """Extract ReasoningResult from input."""
        if isinstance(input_data, ReasoningResult):
            return input_data
        elif isinstance(input_data, dict):
            result = input_data.get("result")
            if isinstance(result, ReasoningResult):
                return result
        return None

    def _extract_answer(self, input_data: Any) -> str:
        """Extract answer text from input."""
        if isinstance(input_data, ReasoningResult):
            return input_data.answer
        elif isinstance(input_data, str):
            return input_data
        elif isinstance(input_data, dict):
            return input_data.get("answer", input_data.get("text", input_data.get("result", "")))
        if hasattr(input_data, "answer"):
            return getattr(input_data, "answer", "")
        return ""

    def _extract_base_confidence(self, input_data: Any) -> float:
        """Extract base confidence from input (0.5 if not provided)."""
        if isinstance(input_data, ReasoningResult):
            return input_data.confidence
        elif isinstance(input_data, dict):
            return input_data.get("confidence", 0.5)
        return 0.5

    def _score_answer_length(self, answer: str, factors: list[str]) -> float:
        """Score based on answer length and detail level."""
        if not answer:
            factors.append("empty_answer: -0.3")
            return 0.2

        score = 0.5
        if len(answer) > 50:
            score += 0.1
            factors.append("answer_length>50: +0.1")
        if len(answer) > 150:
            score += 0.05
            factors.append("answer_length>150: +0.05")
        if len(answer) < 30:
            score -= 0.2
            factors.append("answer_too_short: -0.2")

        return max(0.1, min(0.95, score))

    def _score_language_certainty(self, answer: str, factors: list[str]) -> float:
        """Score based on certainty vs hedging language."""
        if not answer:
            return 0.5

        answer_lower = answer.lower()
        score = 0.5

        # Check certainty markers
        certainty_count = sum(
            1 for m in CERTAINTY_MARKERS_EN + CERTAINTY_MARKERS_ES
            if m in answer_lower
        )
        if certainty_count > 0:
            score += 0.05 * certainty_count
            factors.append(f"certainty_markers({certainty_count}): +{0.05 * certainty_count:.2f}")

        # Check hedging markers
        hedging_count = sum(
            1 for m in HEDGING_MARKERS_EN + HEDGING_MARKERS_ES
            if m in answer_lower
        )
        if hedging_count > 0:
            score -= 0.1 * hedging_count
            factors.append(f"hedging_markers({hedging_count}): -{0.1 * hedging_count:.2f}")

        return max(0.1, min(0.95, score))

    def _score_security_risks(self, answer: str, factors: list[str]) -> float:
        """Score based on security risk detection (highest impact)."""
        if not answer:
            return 0.5

        score = 0.8  # Start high, deduct for risks
        for pattern in SECURITY_RISK_PATTERNS:
            if re.search(pattern, answer):
                score -= 0.3
                factors.append(f"security_risk({pattern}): -0.3")

        return max(0.05, min(0.95, score))

    def _score_quality(self, answer: str, factors: list[str]) -> float:
        """Score based on quality indicators."""
        if not answer:
            return 0.5

        score = 0.6
        for issue in QUALITY_ISSUES:
            if issue in answer:
                score -= 0.1
                factors.append(f"quality_issue({issue}): -0.1")

        # Positive: error handling mentions
        if any(kw in answer.lower() for kw in ["error", "exception", "try", "except"]):
            score += 0.05
            factors.append("error_handling_mentioned: +0.05")

        # Positive: validation mentions
        if any(kw in answer.lower() for kw in ["valid", "check", "verify", "assert"]):
            score += 0.05
            factors.append("validation_mentioned: +0.05")

        return max(0.1, min(0.95, score))

    def _score_step_completeness(
        self, result: Optional[ReasoningResult], factors: list[str]
    ) -> float:
        """Score based on reasoning step completeness."""
        if not result or not result.steps:
            factors.append("no_steps_provided: neutral")
            return 0.5

        score = 0.5
        total_steps = len(result.steps)

        # Having steps is good
        if total_steps >= 2:
            score += 0.1
            factors.append(f"steps_present({total_steps}): +0.1")

        # All steps having conclusions is better
        steps_with_conclusions = sum(
            1 for s in result.steps if s.conclusion
        )
        if steps_with_conclusions == total_steps and total_steps > 0:
            score += 0.1
            factors.append("all_steps_have_conclusions: +0.1")
        elif steps_with_conclusions < total_steps:
            missing = total_steps - steps_with_conclusions
            factors.append(f"incomplete_conclusions({missing} missing): -0.05")

        # Average step confidence
        if total_steps > 0:
            avg_conf = sum(s.confidence for s in result.steps) / total_steps
            if avg_conf > 0.7:
                score += 0.05
                factors.append(f"high_step_confidence({avg_conf:.2f}): +0.05")

        return max(0.1, min(0.95, score))

    def _score_template_match(
        self, result: Optional[ReasoningResult], factors: list[str]
    ) -> float:
        """Score bonus for matching a known template."""
        if not result:
            return 0.5

        template_used = result.template_used
        if template_used and template_used != "generic":
            factors.append(f"template_match({template_used}): +0.15")
            return 0.7
        elif template_used == "generic":
            factors.append("generic_template: neutral")
            return 0.5

        return 0.5

    def estimate_with_evidence(
        self, result: Any, evidence_for: list[str] = None, evidence_against: list[str] = None
    ) -> ConfidenceResult:
        """
        Estimate confidence with explicit evidence lists.

        Args:
            result: The reasoning result to evaluate
            evidence_for: List of supporting evidence descriptions
            evidence_against: List of contradicting evidence descriptions
        """
        base = self.execute(result)

        evidence_for = evidence_for or []
        evidence_against = evidence_against or []

        # Adjust score based on evidence counts
        adjustment = len(evidence_for) * 0.03 - len(evidence_against) * 0.05
        adjusted_score = max(0.05, min(0.95, base.score + adjustment))

        # Update factors
        all_factors = base.factors[:]
        if evidence_for:
            all_factors.append(f"evidence_for({len(evidence_for)}): +{len(evidence_for) * 0.03:.2f}")
        if evidence_against:
            all_factors.append(f"evidence_against({len(evidence_against)}): -{len(evidence_against) * 0.05:.2f}")

        # Recalculate recommendation
        if adjusted_score >= THRESHOLD_PROCEED:
            recommendation = "proceed"
        elif adjusted_score >= THRESHOLD_CAUTION:
            recommendation = "caution"
        else:
            recommendation = "reject"

        return ConfidenceResult(
            score=round(adjusted_score, 2),
            factors=all_factors,
            recommendation=recommendation,
            source="deterministic",
        )

    def fallback(self, input_data: Any) -> ConfidenceResult:
        """Fallback: Return low confidence with caution recommendation."""
        return ConfidenceResult(
            score=0.25,
            factors=["fallback: no evaluation possible"],
            recommendation="caution",
            source="fallback",
        )
