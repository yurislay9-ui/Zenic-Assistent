"""
Tests for extended StepDispatcher action types:
PATCH_FIX, QUALITY_REPORT, EXPLAIN_CODE, SEARCH_DEFINITION,
TRACE_EXECUTION, QUICK_ANALYSIS, CHECK_DEPENDENCIES,
ANALYZE_AND_RESPOND, FULL_ANALYSIS, validation actions,
SCAFFOLD_FRACTAL
"""

import pytest
from unittest.mock import MagicMock

from .conftest import make_step, make_intent, make_plan


class TestOtherActions:
    """Tests for PATCH_FIX, QUALITY_REPORT, EXPLAIN_CODE, etc."""

    @pytest.mark.asyncio
    async def test_patch_fix(self, dispatcher, mock_orchestrator):
        """PATCH_FIX should apply fix via analysis utils."""
        step = make_step("PATCH_FIX")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "broken code", "", [], "python", {}, make_plan(),
        )
        assert r_code == "def fixed(): pass"
        assert "Fix patch applied" in explanations

    @pytest.mark.asyncio
    async def test_quality_report_with_code(self, dispatcher, mock_orchestrator):
        """QUALITY_REPORT should generate report when code present."""
        step = make_step("QUALITY_REPORT")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "x=1", "", [], "python", {}, make_plan(),
        )
        assert any("Quality" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_explain_code_with_code(self, dispatcher, mock_orchestrator):
        """EXPLAIN_CODE should explain when code present."""
        step = make_step("EXPLAIN_CODE")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "def foo(): pass", "", [], "python", {}, make_plan(),
        )
        assert any("This code does X" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_explain_code_without_code(self, dispatcher, mock_orchestrator):
        """EXPLAIN_CODE should explain concept when no code."""
        step = make_step("EXPLAIN_CODE")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        assert any("Concept explanation" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_search_definition_found(self, dispatcher, mock_orchestrator):
        """SEARCH_DEFINITION should find nodes in AST engine."""
        step = make_step("SEARCH_DEFINITION")
        intent = make_intent(target="test_func")
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert any("Found:" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_search_definition_not_found(self, dispatcher, mock_orchestrator):
        """SEARCH_DEFINITION should report when target not found."""
        mock_orchestrator.ast_engine.get_node_info.return_value = []
        step = make_step("SEARCH_DEFINITION")
        intent = make_intent(target="missing")
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert any("not found" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_trace_execution(self, dispatcher, mock_orchestrator):
        """TRACE_EXECUTION should trace function names."""
        step = make_step("TRACE_EXECUTION")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert any("Symbolic execution trace" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_quick_analysis(self, dispatcher):
        """QUICK_ANALYSIS should append completion message."""
        step = make_step("QUICK_ANALYSIS")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert any("Quick analysis completed" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_check_dependencies(self, dispatcher, mock_orchestrator):
        """CHECK_DEPENDENCIES should extend explanations with deps."""
        step = make_step("CHECK_DEPENDENCIES")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert "dep1" in explanations
        assert "dep2" in explanations

    @pytest.mark.asyncio
    async def test_analyze_and_respond_with_code(self, dispatcher, mock_orchestrator):
        """ANALYZE_AND_RESPOND should use analysis utils when code present."""
        step = make_step("ANALYZE_AND_RESPOND")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert "Analysis result" in explanations

    @pytest.mark.asyncio
    async def test_full_analysis_with_code(self, dispatcher, mock_orchestrator):
        """FULL_ANALYSIS should produce full analysis when code present."""
        step = make_step("FULL_ANALYSIS")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert "Full analysis result" in explanations


class TestValidationActions:
    """Tests for SYMBOLIC_VALIDATION and SYNTAX_VALIDATION."""

    @pytest.mark.asyncio
    async def test_symbolic_validation_without_agent(self, dispatcher):
        """SYMBOLIC_VALIDATION should append bounded execution message without agent."""
        step = make_step("SYMBOLIC_VALIDATION")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert any("Symbolic validation" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_syntax_validation_without_agent(self, dispatcher):
        """SYNTAX_VALIDATION should behave like symbolic validation without agent."""
        step = make_step("SYNTAX_VALIDATION")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert any("validation" in e.lower() for e in explanations)

    @pytest.mark.asyncio
    async def test_validation_with_agent(self, dispatcher, mock_orchestrator):
        """SYMBOLIC_VALIDATION should use ValidationAgent when available."""
        mock_output = MagicMock()
        mock_output.issues = []
        mock_output.risk_score = 0.1
        mock_output.source = "F5"
        mock_validation = MagicMock()
        mock_validation.validate_with_runner.return_value = mock_output
        mock_orchestrator._validation_agent = mock_validation
        mock_orchestrator._agent_runner = MagicMock()

        step = make_step("SYMBOLIC_VALIDATION")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert any("No issues found" in e or "validation" in e.lower() for e in explanations)


class TestScaffoldFractal:
    """Tests for SCAFFOLD_FRACTAL action type."""

    @pytest.mark.asyncio
    async def test_fractal_not_available(self, dispatcher, mock_orchestrator):
        """Should report fractal not available when _fractal_gen is None."""
        mock_orchestrator._fractal_gen = None
        step = make_step("SCAFFOLD_FRACTAL")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        assert any("Not available" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_fractal_not_available_no_attr(self, dispatcher, mock_orchestrator):
        """Should handle missing _fractal_gen attribute gracefully."""
        del mock_orchestrator._fractal_gen
        step = make_step("SCAFFOLD_FRACTAL")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        assert any("Not available" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_fractal_with_generator(self, dispatcher, mock_orchestrator):
        """Should attempt fractal generation when generator is available."""
        mock_result = MagicMock()
        mock_result.spec = None
        mock_result.files_generated = []
        mock_result.current_phase = 1
        mock_fractal = MagicMock()
        mock_fractal.generate_project.return_value = mock_result
        mock_orchestrator._fractal_gen = mock_fractal

        step = make_step("SCAFFOLD_FRACTAL")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        mock_fractal.generate_project.assert_called_once()
