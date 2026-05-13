"""
Tests for Intent, Reasoning, and Business schemas.
"""

import pytest
from dataclasses import fields

from src.core.agents.schemas import (
    IntentInput, IntentOutput,
    ReasoningInput, ReasoningStep, ReasoningOutput,
    BusinessInput, BusinessOutput,
)


# ============================================================
#  INTENT SCHEMAS
# ============================================================

class TestIntentInput:
    """Tests for IntentInput schema."""

    def test_default_values(self):
        """Should have empty string defaults."""
        inp = IntentInput()
        assert inp.message == ""
        assert inp.context == ""

    def test_custom_values(self):
        """Should accept custom values."""
        inp = IntentInput(message="create API", context="web app")
        assert inp.message == "create API"
        assert inp.context == "web app"


class TestIntentOutput:
    """Tests for IntentOutput schema."""

    def test_default_values(self):
        """Should have valid defaults for all fields."""
        out = IntentOutput()
        assert out.operation == "SEARCH"
        assert out.goal == "FEATURE_ADD"
        assert out.target == ""
        assert out.language == "python"
        assert out.entities == {}
        assert out.template_type == "generic"
        assert out.criticality == "standard"
        assert out.confidence == 0.0
        assert out.source == "fallback"

    def test_custom_operation(self):
        """Should accept valid operation values."""
        for op in ["CREATE", "REFACTOR", "DELETE", "SEARCH", "ANALYZE", "EXPLAIN", "DEBUG", "OPTIMIZE"]:
            out = IntentOutput(operation=op)
            assert out.operation == op

    def test_custom_criticality(self):
        """Should accept valid criticality values."""
        for crit in ["standard", "moderate", "critical"]:
            out = IntentOutput(criticality=crit)
            assert out.criticality == crit


# ============================================================
#  REASONING SCHEMAS
# ============================================================

class TestReasoningInput:
    """Tests for ReasoningInput schema."""

    def test_default_values(self):
        """Should have sensible defaults."""
        inp = ReasoningInput()
        assert inp.query == ""
        assert inp.mode == "step_by_step"
        assert inp.context == ""
        assert inp.max_steps == 5

    def test_custom_mode(self):
        """Should accept valid mode values."""
        for mode in ["step_by_step", "self_reflect", "with_context"]:
            inp = ReasoningInput(mode=mode)
            assert inp.mode == mode


class TestReasoningStep:
    """Tests for ReasoningStep schema."""

    def test_default_values(self):
        """Should have zero/empty defaults."""
        step = ReasoningStep()
        assert step.step_number == 0
        assert step.description == ""
        assert step.conclusion == ""

    def test_custom_values(self):
        """Should accept custom values."""
        step = ReasoningStep(step_number=1, description="Analyze", conclusion="Done")
        assert step.step_number == 1
        assert step.description == "Analyze"


class TestReasoningOutput:
    """Tests for ReasoningOutput schema."""

    def test_default_values(self):
        """Should have empty defaults."""
        out = ReasoningOutput()
        assert out.answer == ""
        assert out.confidence == 0.0
        assert out.steps == []
        assert out.refinements == 0
        assert out.source == "fallback"

    def test_with_steps(self):
        """Should accept a list of ReasoningStep."""
        steps = [ReasoningStep(step_number=i, description=f"Step {i}") for i in range(3)]
        out = ReasoningOutput(answer="yes", steps=steps)
        assert len(out.steps) == 3
        assert out.steps[0].step_number == 0


# ============================================================
#  BUSINESS SCHEMAS
# ============================================================

class TestBusinessInput:
    """Tests for BusinessInput schema."""

    def test_default_values(self):
        """Should have empty defaults."""
        inp = BusinessInput()
        assert inp.operation_type == ""
        assert inp.data == {}
        assert inp.context == {}
        assert inp.description == ""

    def test_custom_values(self):
        """Should accept custom operation types and data."""
        inp = BusinessInput(operation_type="invoice", data={"amount": 100})
        assert inp.operation_type == "invoice"
        assert inp.data["amount"] == 100


class TestBusinessOutput:
    """Tests for BusinessOutput schema."""

    def test_default_values(self):
        """Should have failure-safe defaults."""
        out = BusinessOutput()
        assert out.success is False
        assert out.data == {}
        assert out.side_effects == []
        assert out.insights == []
        assert out.errors == []
        assert out.source == "fallback"

    def test_successful_output(self):
        """Should accept successful output data."""
        out = BusinessOutput(success=True, data={"total": 150.0}, insights=["tax applied"])
        assert out.success is True
        assert out.data["total"] == 150.0
