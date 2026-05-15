"""
Tests for Layer 7: Reasoning agents (A35-A39).

All 5 agents tested:
  - A35 ProblemDetector
  - A36 StepDecomposer
  - A37 TemplateReasoner
  - A38 ConfidenceEstimator
  - A39 ConclusionExtractor
"""

import pytest

from src.core.agents.reasoning import (
    ProblemDetector,
    StepDecomposer,
    TemplateReasoner,
    ConfidenceEstimator,
    ConclusionExtractor,
)
from src.core.agents.schemas import (
    ProblemType,
    ReasoningStep,
    ReasoningResult,
    DecomposedSteps,
    ConfidenceResult,
    Conclusion,
)


# ═══════════════════════════════════════════════════════════
# A35 ProblemDetector Tests
# ═══════════════════════════════════════════════════════════



class TestConclusionExtractor:
    """A39: Extract the final conclusion from reasoning steps."""

    def setup_method(self):
        self.extractor = ConclusionExtractor()

    def test_extract_from_reasoning_result(self):
        """Should extract conclusion from ReasoningResult."""
        result = ReasoningResult(
            answer="Build an API with endpoints and error handling.",
            template_used="api",
            confidence=0.8,
            steps=[
                ReasoningStep(step_number=1, description="Identify endpoints", conclusion="Endpoints identified", confidence=0.8),
                ReasoningStep(step_number=2, description="Implement handlers", conclusion="Handlers implemented", confidence=0.75),
                ReasoningStep(step_number=3, description="Add error handling", conclusion="Therefore the API is complete with proper error handling", confidence=0.85),
            ],
        )
        conclusion = self.extractor.execute(result)
        assert isinstance(conclusion, Conclusion)
        assert conclusion.text != ""
        assert conclusion.strength > 0.0

    def test_conclusion_marker_en(self):
        """'therefore' should be recognized as conclusion marker."""
        result = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="therefore the answer is 42", confidence=0.8),
            ],
        )
        conclusion = self.extractor.execute(result)
        assert "42" in conclusion.text or "answer" in conclusion.text.lower()

    def test_conclusion_marker_es(self):
        """'por lo tanto' should be recognized as conclusion marker."""
        result = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Paso 1", conclusion="por lo tanto la respuesta es correcta", confidence=0.8),
            ],
        )
        conclusion = self.extractor.execute(result)
        assert "correcta" in conclusion.text or "respuesta" in conclusion.text.lower()

    def test_last_step_conclusion(self):
        """Without markers, last step conclusion should be used."""
        result = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="First step done", confidence=0.7),
                ReasoningStep(step_number=2, description="Step 2", conclusion="Final implementation complete", confidence=0.8),
            ],
        )
        conclusion = self.extractor.execute(result)
        assert "Final implementation complete" in conclusion.text

    def test_extract_from_decomposed_steps(self):
        """Should extract from DecomposedSteps object."""
        steps = DecomposedSteps(
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="Analyzed requirements", confidence=0.8),
                ReasoningStep(step_number=2, description="Step 2", conclusion="In conclusion the system is ready", confidence=0.85),
            ],
            dependencies=["step_2 depends on step_1"],
            order=[1, 2],
        )
        conclusion = self.extractor.execute(steps)
        assert conclusion.text != ""
        assert "system is ready" in conclusion.text or "conclusion" in conclusion.text.lower()

    def test_extract_from_string(self):
        """Should extract from raw text string."""
        text = "After careful analysis, therefore the best approach is to use FastAPI with SQLite."
        conclusion = self.extractor.execute(text)
        assert conclusion.text != ""
        assert "FastAPI" in conclusion.text or "best approach" in conclusion.text

    def test_supporting_steps_populated(self):
        """supported_by should list supporting step conclusions."""
        result = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="Endpoints identified", confidence=0.8),
                ReasoningStep(step_number=2, description="Step 2", conclusion="Handlers implemented", confidence=0.75),
                ReasoningStep(step_number=3, description="Step 3", conclusion="Therefore API is complete", confidence=0.85),
            ],
        )
        conclusion = self.extractor.execute(result)
        assert len(conclusion.supported_by) > 0

    def test_strength_increases_with_steps(self):
        """More supporting steps should increase conclusion strength."""
        two_steps = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="First", confidence=0.7),
                ReasoningStep(step_number=2, description="Step 2", conclusion="Final answer", confidence=0.7),
            ],
        )
        five_steps = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=i + 1, description=f"Step {i+1}", conclusion=f"Conclusion {i+1}", confidence=0.7)
                for i in range(5)
            ],
        )
        two_conc = self.extractor.execute(two_steps)
        five_conc = self.extractor.execute(five_steps)
        assert five_conc.strength >= two_conc.strength

    def test_certainty_markers_boost_strength(self):
        """Certainty markers should boost conclusion strength."""
        certain = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="certainly the correct answer", confidence=0.7),
            ],
        )
        neutral = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="a possible answer", confidence=0.7),
            ],
        )
        certain_conc = self.extractor.execute(certain)
        neutral_conc = self.extractor.execute(neutral)
        assert certain_conc.strength >= neutral_conc.strength

    def test_empty_input(self):
        """Empty input should return empty conclusion."""
        conclusion = self.extractor.execute(ReasoningResult(answer="", steps=[]))
        assert conclusion.text == ""
        assert conclusion.strength == 0.0

    def test_extract_summary_convenience(self):
        """extract_summary should return just the text."""
        result = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="The result is 42", confidence=0.8),
            ],
        )
        text = self.extractor.extract_summary(result)
        assert isinstance(text, str)
        assert "42" in text

    def test_conclusion_from_answer_text(self):
        """Should extract conclusion from answer text when steps lack conclusions."""
        result = ReasoningResult(
            answer="After analysis, therefore the solution is to use JWT tokens for authentication.",
            steps=[],
        )
        conclusion = self.extractor.execute(result)
        assert conclusion.text != ""

    def test_max_conclusion_length(self):
        """Conclusion should be capped at MAX_CONCLUSION_LENGTH."""
        long_conclusion = "A" * 500
        result = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion=long_conclusion, confidence=0.7),
            ],
        )
        conclusion = self.extractor.execute(result)
        assert len(conclusion.text) <= 300

    def test_fallback_returns_empty(self):
        """Fallback should return empty conclusion."""
        conclusion = self.extractor.fallback(None)
        assert conclusion.text == ""
        assert conclusion.strength == 0.0
        assert conclusion.source == "fallback"


# ═══════════════════════════════════════════════════════════
# Integration: Full Reasoning Pipeline Test
# ═══════════════════════════════════════════════════════════

