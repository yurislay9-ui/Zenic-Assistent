"""
Tests for agent schemas and base agent/result classes.
"""

import json
import pytest

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import (
    IntentInput, IntentOutput,
    ReasoningInput, ReasoningOutput, ReasoningStep,
    BusinessInput, BusinessOutput,
    CodeInput, CodeOutput, FileSpec,
    AutomationInput, AutomationOutput, TriggerSpec, ActionSpec, ScheduleSpec,
    ValidationInput, ValidationOutput, ValidationIssue,
)

from .conftest import SampleAgent, BrokenAgent


# ============================================================
#  SCHEMA TESTS
# ============================================================

class TestSchemas:
    """Tests para los esquemas de datos de los agentes."""

    def test_intent_input_defaults(self):
        inp = IntentInput()
        assert inp.message == ""
        assert inp.context == ""

    def test_intent_input_with_data(self):
        inp = IntentInput(message="Create a login page", context="web app")
        assert inp.message == "Create a login page"
        assert inp.context == "web app"

    def test_intent_output_defaults(self):
        out = IntentOutput()
        assert out.operation == "SEARCH"
        assert out.goal == "FEATURE_ADD"
        assert out.confidence == 0.0
        assert out.source == "fallback"

    def test_intent_output_with_data(self):
        out = IntentOutput(operation="CREATE", goal="FEATURE_ADD",
                          confidence=0.9, source="llm",
                          target="auth.py", language="python")
        assert out.operation == "CREATE"
        assert out.confidence == 0.9
        assert out.source == "llm"

    def test_reasoning_input_defaults(self):
        inp = ReasoningInput()
        assert inp.mode == "step_by_step"
        assert inp.max_steps == 5

    def test_reasoning_output_with_steps(self):
        steps = [
            ReasoningStep(step_number=1, description="Analyze", conclusion="Found X"),
            ReasoningStep(step_number=2, description="Verify", conclusion="Confirmed"),
        ]
        out = ReasoningOutput(answer="Yes", confidence=0.8, steps=steps, source="llm")
        assert len(out.steps) == 2
        assert out.steps[0].conclusion == "Found X"

    def test_business_input(self):
        inp = BusinessInput(
            operation_type="invoice",
            data={"amount": 100, "tax_rate": 0.21},
            description="Calculate invoice total",
        )
        assert inp.operation_type == "invoice"
        assert inp.data["amount"] == 100

    def test_business_output(self):
        out = BusinessOutput(
            success=True,
            data={"total": 121},
            side_effects=["notify_accounting"],
            insights=["Tax rate is 21%"],
        )
        assert out.success is True
        assert len(out.insights) == 1

    def test_code_input(self):
        inp = CodeInput(task="generate", requirements="FastAPI app",
                       language="python")
        assert inp.task == "generate"
        assert inp.language == "python"

    def test_code_output_with_files(self):
        files = [FileSpec(path="main.py", content="print('hi')", language="python")]
        out = CodeOutput(code="print('hi')", files=files, source="llm")
        assert len(out.files) == 1
        assert out.files[0].path == "main.py"

    def test_automation_input(self):
        inp = AutomationInput(description="Email me every Friday")
        assert inp.description == "Email me every Friday"

    def test_automation_output(self):
        triggers = [TriggerSpec(type="schedule", config={"day": "friday"})]
        actions = [ActionSpec(type="email", config={"to": "user@test.com"})]
        schedule = ScheduleSpec(type="cron", cron_expression="0 17 * * 5")

        out = AutomationOutput(
            name="friday_email",
            triggers=triggers,
            actions=actions,
            schedule=schedule,
        )
        assert out.name == "friday_email"
        assert len(out.triggers) == 1
        assert out.schedule.cron_expression == "0 17 * * 5"

    def test_validation_input(self):
        inp = ValidationInput(target="code", content="eval(input())", language="python")
        assert inp.target == "code"

    def test_validation_output(self):
        issues = [
            ValidationIssue(severity="error", code="DANGEROUS_CALL",
                           message="eval() is dangerous", suggestion="Use ast.literal_eval()"),
        ]
        out = ValidationOutput(is_valid=False, issues=issues, risk_score=0.9)
        assert out.is_valid is False
        assert len(out.issues) == 1
        assert out.issues[0].severity == "error"


# ============================================================
#  BASE AGENT TESTS
# ============================================================

class TestBaseAgent:
    """Tests para la clase BaseAgent."""

    def test_agent_creation(self):
        agent = SampleAgent()
        assert agent.name == "test_agent"
        assert agent._call_count == 0

    def test_agent_stats(self):
        agent = SampleAgent()
        stats = agent.stats
        assert stats["name"] == "test_agent"
        assert stats["total_calls"] == 0

    def test_agent_update_stats_llm(self):
        agent = SampleAgent()
        agent._update_stats("llm", 150)
        assert agent._call_count == 1
        assert agent._llm_success_count == 1
        assert agent._total_duration_ms == 150

    def test_agent_update_stats_fallback(self):
        agent = SampleAgent()
        agent._update_stats("fallback", 5)
        assert agent._fallback_count == 1

    def test_agent_update_stats_cache(self):
        agent = SampleAgent()
        agent._update_stats("cache", 0)
        assert agent._cache_hit_count == 1

    def test_agent_update_stats_with_error(self):
        agent = SampleAgent()
        agent._update_stats("fallback", 5, error="timeout")
        assert agent._last_error == "timeout"

    def test_extract_json_from_markdown(self):
        text = '```json\n{"operation": "CREATE", "goal": "FEATURE_ADD"}\n```'
        result = BaseAgent.extract_json(text)
        assert result is not None
        assert result["operation"] == "CREATE"

    def test_extract_json_from_raw(self):
        text = 'Here is the result: {"operation": "SEARCH"}'
        result = BaseAgent.extract_json(text)
        assert result is not None
        assert result["operation"] == "SEARCH"

    def test_extract_json_invalid(self):
        text = "No JSON here at all"
        result = BaseAgent.extract_json(text)
        assert result is None

    def test_extract_json_nested(self):
        text = '{"outer": {"inner": "value"}, "list": [1, 2]}'
        result = BaseAgent.extract_json(text)
        assert result is not None
        assert result["outer"]["inner"] == "value"

    def test_extract_list_numbered(self):
        text = "1. First item\n2. Second item\n3. Third item"
        result = BaseAgent.extract_list(text)
        assert len(result) == 3
        assert "First item" in result[0]

    def test_extract_list_bullets(self):
        text = "- Item one\n- Item two\n* Item three"
        result = BaseAgent.extract_list(text)
        assert len(result) == 3

    def test_extract_list_empty(self):
        result = BaseAgent.extract_list("No list items here")
        assert result == []

    def test_clean_llm_text_think_block(self):
        text = " The answer is 42"
        result = BaseAgent.clean_llm_text(text)
        assert "think" not in result
        assert "42" in result

    def test_clean_llm_text_markdown(self):
        text = "```python\ndef hello():\n    pass\n```"
        result = BaseAgent.clean_llm_text(text)
        assert "```" not in result
        assert "def hello" in result

    def test_clean_llm_text_bold(self):
        text = "This is **important** text"
        result = BaseAgent.clean_llm_text(text)
        assert "**" not in result
        assert "important" in result

    def test_validate_output_default(self):
        agent = SampleAgent()
        assert agent.validate_output("something") is True
        assert agent.validate_output(None) is False

    def test_fallback_returns_valid_output(self):
        agent = SampleAgent()
        result = agent.fallback("test input")
        assert isinstance(result, IntentOutput)
        assert result.source == "fallback"
        assert result.confidence == 0.1

    def test_build_prompt(self):
        agent = SampleAgent()
        sys_prompt, user_prompt = agent.build_prompt("Create a user")
        assert "test agent" in sys_prompt
        assert "Create a user" in user_prompt

    def test_parse_response_valid(self):
        agent = SampleAgent()
        result = agent.parse_response(
            '{"operation": "CREATE", "goal": "FEATURE_ADD", "confidence": 0.9}',
            "test"
        )
        assert result is not None
        assert result.operation == "CREATE"
        assert result.confidence == 0.9

    def test_parse_response_invalid(self):
        agent = SampleAgent()
        result = agent.parse_response("not json at all", "test")
        assert result is None


# ============================================================
#  AGENT RESULT TESTS
# ============================================================

class TestAgentResult:
    """Tests para AgentResult."""

    def test_success_result(self):
        r = AgentResult(success=True, data={"key": "value"}, source="llm", duration_ms=150)
        assert r.success is True
        assert r.data["key"] == "value"
        assert r.source == "llm"
        assert r.cache_hit is False

    def test_fallback_result(self):
        r = AgentResult(success=True, data=None, source="fallback")
        assert r.source == "fallback"

    def test_error_result(self):
        r = AgentResult(success=False, data=None, source="error", error="timeout")
        assert r.success is False
        assert r.error == "timeout"

    def test_cache_hit_result(self):
        r = AgentResult(success=True, data=None, source="cache", cache_hit=True)
        assert r.cache_hit is True

    def test_repr(self):
        r = AgentResult(success=True, source="llm", duration_ms=100)
        assert "success=True" in repr(r)
        assert "llm" in repr(r)
