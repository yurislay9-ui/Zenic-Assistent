"""
Tests for core StepDispatcher action types:
ANALYZE_STRUCTURE, SCRAPE_PATTERNS, GENERATE_CODE,
REPLACE_AST_NODE, DELETE_AST_NODE
"""

import pytest
from unittest.mock import AsyncMock

from .conftest import make_step, make_intent, make_plan


class TestAnalyzeStructure:
    """Tests for ANALYZE_STRUCTURE action type."""

    @pytest.mark.asyncio
    async def test_analyze_with_code(self, dispatcher, mock_orchestrator):
        """Should analyze structure when code is provided."""
        step = make_step("ANALYZE_STRUCTURE")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "def foo(): pass", "", [], "python", {}, make_plan(),
        )
        assert len(explanations) == 1
        assert "Structure:" in explanations[0]
        assert "3 functions" in explanations[0]

    @pytest.mark.asyncio
    async def test_analyze_without_code(self, dispatcher):
        """Should append no-code message when code is empty."""
        step = make_step("ANALYZE_STRUCTURE")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        assert len(explanations) == 1
        assert "No code provided" in explanations[0]

    @pytest.mark.asyncio
    async def test_analyze_returns_code_unchanged(self, dispatcher):
        """Should not modify code or result_code for ANALYZE_STRUCTURE."""
        step = make_step("ANALYZE_STRUCTURE")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "x=1", "", [], "python", {}, make_plan(),
        )
        assert code == "x=1"
        assert r_code == ""


class TestScrapePatterns:
    """Tests for SCRAPE_PATTERNS action type."""

    @pytest.mark.asyncio
    async def test_scrape_smart_fetch_success(self, dispatcher, mock_orchestrator):
        """Should use smart_fetch result when successful."""
        step = make_step("SCRAPE_PATTERNS")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        assert len(explanations) >= 1
        assert "SmartScraper" in explanations[0]

    @pytest.mark.asyncio
    async def test_scrape_uses_constraints_query(self, dispatcher, mock_orchestrator):
        """Should prefer constraints query over intent.scrap_query."""
        step = make_step("SCRAPE_PATTERNS", constraints={"query": "oauth patterns"})
        intent = make_intent()
        await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        mock_orchestrator.scrap.smart_fetch.assert_called_once_with("oauth patterns", "python")

    @pytest.mark.asyncio
    async def test_scrape_fallback_when_smart_fails(self, dispatcher, mock_orchestrator):
        """Should fallback to fetch_all_sources when smart_fetch fails."""
        mock_orchestrator.scrap.smart_fetch = AsyncMock(return_value={"success": False})
        step = make_step("SCRAPE_PATTERNS")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        mock_orchestrator.scrap.fetch_all_sources.assert_called_once()


class TestGenerateCode:
    """Tests for GENERATE_CODE action type."""

    @pytest.mark.asyncio
    async def test_generate_code(self, dispatcher, mock_orchestrator):
        """Should call code_gen.generate_contextual_code and return result."""
        step = make_step("GENERATE_CODE")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        assert r_code == "def new_func(): pass"
        assert any("Code generated" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_generate_code_uses_intent_op(self, dispatcher, mock_orchestrator):
        """Should pass intent.op to generate_contextual_code."""
        step = make_step("GENERATE_CODE")
        intent = make_intent(op="REFACTOR")
        await dispatcher.execute_step(
            step, intent, "x=1", "", [], "python", {}, make_plan(),
        )
        mock_orchestrator._code_gen.generate_contextual_code.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_code_explains_intent(self, dispatcher, mock_orchestrator):
        """Should explain which operation code was generated for."""
        step = make_step("GENERATE_CODE")
        intent = make_intent(op="CREATE")
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        assert any("CREATE" in e for e in explanations)


class TestReplaceAstNode:
    """Tests for REPLACE_AST_NODE action type."""

    @pytest.mark.asyncio
    async def test_replace_with_code_and_target(self, dispatcher, mock_orchestrator):
        """Should perform AST surgery when code and target_node_name are present."""
        step = make_step("REPLACE_AST_NODE", target_node_name="old_func")
        intent = make_intent()
        plan = make_plan(solver_proof={})
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "def old_func(): pass", "", [], "python", {}, plan,
        )
        assert r_code == "def replaced(): pass"
        mock_orchestrator.surgeon.mutate_node.assert_called_once()

    @pytest.mark.asyncio
    async def test_replace_fallback_without_target(self, dispatcher, mock_orchestrator):
        """Should fall back to contextual code generation without target."""
        step = make_step("REPLACE_AST_NODE", target_node_name="")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "def x(): pass", "", [], "python", {}, make_plan(),
        )
        mock_orchestrator._code_gen.generate_contextual_code.assert_called_once()
        assert "Optimized code generated" in explanations

    @pytest.mark.asyncio
    async def test_replace_with_ai_suggestion(self, dispatcher, mock_orchestrator):
        """Should use MiniAI pattern suggestion when AI is loaded."""
        mock_orchestrator._ai.is_loaded = True
        step = make_step("REPLACE_AST_NODE", target_node_name="target_func")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert any("MiniAI suggests pattern" in e for e in explanations)


class TestDeleteAstNode:
    """Tests for DELETE_AST_NODE action type."""

    @pytest.mark.asyncio
    async def test_delete_with_code_and_target(self, dispatcher, mock_orchestrator):
        """Should delete the AST node via surgeon."""
        step = make_step("DELETE_AST_NODE", target_node_name="unused_func")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "def unused_func(): pass", "", [], "python", {}, make_plan(),
        )
        assert r_code == "# deleted"
        mock_orchestrator.surgeon.delete_function.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_without_target(self, dispatcher, mock_orchestrator):
        """Should do nothing when no target node name provided."""
        step = make_step("DELETE_AST_NODE", target_node_name="")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        mock_orchestrator.surgeon.delete_function.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_explains_removal(self, dispatcher, mock_orchestrator):
        """Should add explanation about deleted function."""
        step = make_step("DELETE_AST_NODE", target_node_name="old_func")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "def old_func(): pass", "", [], "python", {}, make_plan(),
        )
        assert any("deleted" in e for e in explanations)
