"""
Tests for PromptBuilder, AgentPrompts, and Orchestrator integration.
"""

import pytest

from src.core.agents.prompts import PromptBuilder, AgentPrompts


# ============================================================
#  PROMPT BUILDER TESTS
# ============================================================

class TestPromptBuilder:
    """Tests para PromptBuilder."""

    def test_build_simple(self):
        sys, user = PromptBuilder.build(
            "You are helpful.", "Process: {message}", {"message": "hello"}
        )
        assert sys == "You are helpful."
        assert user == "Process: hello"

    def test_build_multiple_vars(self):
        sys, user = PromptBuilder.build(
            "System", "Task: {task}, Lang: {language}",
            {"task": "generate", "language": "python"}
        )
        assert "generate" in user
        assert "python" in user

    def test_build_missing_var(self):
        """Missing vars should remain as placeholders."""
        sys, user = PromptBuilder.build(
            "System", "Task: {task}, Missing: {missing}",
            {"task": "generate"}
        )
        assert "generate" in user
        assert "{missing}" in user

    def test_build_dict_value(self):
        sys, user = PromptBuilder.build(
            "System", "Data: {data}", {"data": {"key": "value"}}
        )
        assert "key" in user
        assert "value" in user

    def test_build_list_value(self):
        sys, user = PromptBuilder.build(
            "System", "Items: {items}", {"items": ["a", "b", "c"]}
        )
        assert "a" in user

    def test_add_context_to_prompt(self):
        prompt = "Base prompt"
        context = {"language": "python", "version": "3.12"}
        result = PromptBuilder.add_context_to_prompt(prompt, context)
        assert "language" in result
        assert "python" in result

    def test_add_context_empty(self):
        prompt = "Base prompt"
        result = PromptBuilder.add_context_to_prompt(prompt, {})
        assert result == "Base prompt"

    def test_add_context_truncation(self):
        prompt = "Base prompt"
        context = {"big": "x" * 1000}
        result = PromptBuilder.add_context_to_prompt(prompt, context, max_chars=100)
        assert len(result) < 200  # Should be truncated


# ============================================================
#  AGENT PROMPTS TESTS
# ============================================================

class TestAgentPrompts:
    """Tests para los system prompts predefinidos."""

    def test_intent_prompt_exists(self):
        assert AgentPrompts.INTENT_SYSTEM != ""
        assert AgentPrompts.INTENT_USER != ""

    def test_reasoning_prompts_exist(self):
        assert AgentPrompts.REASONING_SYSTEM_STEP_BY_STEP != ""
        assert AgentPrompts.REASONING_SYSTEM_SELF_REFLECT != ""
        assert AgentPrompts.REASONING_SYSTEM_WITH_CONTEXT != ""

    def test_business_prompt_exists(self):
        assert AgentPrompts.BUSINESS_SYSTEM != ""

    def test_code_prompts_exist(self):
        assert AgentPrompts.CODE_SYSTEM_GENERATE != ""
        assert AgentPrompts.CODE_SYSTEM_TRANSFORM != ""
        assert AgentPrompts.CODE_SYSTEM_SCAFFOLD != ""

    def test_automation_prompt_exists(self):
        assert AgentPrompts.AUTOMATION_SYSTEM != ""

    def test_validation_prompt_exists(self):
        assert AgentPrompts.VALIDATION_SYSTEM != ""

    def test_intent_prompt_contains_json_instruction(self):
        assert "JSON" in AgentPrompts.INTENT_SYSTEM

    def test_validation_prompt_contains_risk_score(self):
        assert "risk_score" in AgentPrompts.VALIDATION_SYSTEM


# ============================================================
#  INTEGRATION: ORCHESTRATOR CABLEADO
# ============================================================

class TestOrchestratorCableado:
    """Tests de integración del Agent Framework con el Orchestrator."""

    def test_orchestrator_has_agent_runner(self):
        """El orchestrator debe tener _agent_runner cableado."""
        from src.core.orchestrator import ZenicOrchestrator
        from src.core.agents.runner import AgentRunner
        orch = ZenicOrchestrator()
        assert hasattr(orch, '_agent_runner')
        assert isinstance(orch._agent_runner, AgentRunner)

    def test_orchestrator_agent_runner_has_ai(self):
        """El AgentRunner del orchestrator debe tener MiniAI cableado."""
        from src.core.orchestrator import ZenicOrchestrator
        orch = ZenicOrchestrator()
        assert orch._agent_runner._mini_ai is not None or orch._ai is not None

    def test_orchestrator_agent_runner_has_cache(self):
        """El AgentRunner del orchestrator debe tener cache habilitado."""
        from src.core.orchestrator import ZenicOrchestrator
        orch = ZenicOrchestrator()
        assert orch._agent_runner._cache is not None
        assert orch._agent_runner._enable_cache is True

    def test_orchestrator_status_includes_agent_framework(self):
        """get_system_status() debe incluir agent_framework stats."""
        from src.core.orchestrator import ZenicOrchestrator
        import asyncio
        orch = ZenicOrchestrator()
        status = asyncio.run(orch.get_system_status())
        assert "agent_framework" in status
        assert "runner_stats" in status["agent_framework"]
        assert "cache_stats" in status["agent_framework"]
