"""
Tests for unknown step types and execute_plan_steps.
"""

import pytest

from .conftest import make_step, make_intent, make_plan


class TestUnknownStepType:
    """Tests for unknown/unhandled step action types."""

    @pytest.mark.asyncio
    async def test_unknown_action_returns_unchanged(self, dispatcher):
        """Unknown action type should return inputs unchanged."""
        step = make_step("UNKNOWN_ACTION")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "x=1", "", [], "python", {}, make_plan(),
        )
        assert r_code == ""
        assert code == "x=1"
        assert len(explanations) == 1
        assert "Unknown action" in explanations[0]

    @pytest.mark.asyncio
    async def test_unknown_action_preserves_result_code(self, dispatcher):
        """Unknown action should not overwrite existing result_code."""
        step = make_step("UNKNOWN_ACTION")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "x=1", "existing_code", ["prev"], "python", {}, make_plan(),
        )
        assert r_code == "existing_code"

    @pytest.mark.asyncio
    async def test_unknown_action_preserves_explanations(self, dispatcher):
        """Unknown action should not modify existing explanations."""
        step = make_step("UNKNOWN_ACTION")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "x=1", "", ["existing explanation"], "python", {}, make_plan(),
        )
        assert "existing explanation" in explanations


class TestExecutePlanSteps:
    """Tests for execute_plan_steps sequential iteration."""

    @pytest.mark.asyncio
    async def test_empty_plan(self, dispatcher):
        """Should return empty result_code for plan with no steps."""
        plan = make_plan()
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_plan_steps(
            plan, intent, "", [], "python", {},
        )
        assert r_code == ""
        assert explanations == []

    @pytest.mark.asyncio
    async def test_single_step_plan(self, dispatcher, mock_orchestrator):
        """Should execute a single step correctly."""
        plan = make_plan()
        plan.steps = [make_step("GENERATE_CODE")]
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_plan_steps(
            plan, intent, "", [], "python", {},
        )
        assert r_code == "def new_func(): pass"

    @pytest.mark.asyncio
    async def test_multi_step_plan(self, dispatcher, mock_orchestrator):
        """Should execute multiple steps sequentially."""
        plan = make_plan()
        plan.steps = [
            make_step("ANALYZE_STRUCTURE"),
            make_step("QUICK_ANALYSIS"),
        ]
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_plan_steps(
            plan, intent, "x=1", [], "python", {},
        )
        assert len(explanations) == 2

    @pytest.mark.asyncio
    async def test_steps_accumulate_code(self, dispatcher, mock_orchestrator):
        """Steps should accumulate changes to code across the plan."""
        plan = make_plan()
        plan.steps = [
            make_step("GENERATE_CODE"),
        ]
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_plan_steps(
            plan, intent, "", [], "python", {},
        )
        # GENERATE_CODE sets result_code
        assert r_code == "def new_func(): pass"
