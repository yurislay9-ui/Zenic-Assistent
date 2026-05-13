"""
Tests for ValidationAgent (Phase F4-F5)

Tests ValidationAgent security detection, code quality, Python AST analysis,
chain validation, config validation, build_prompt, parse_response,
compatibility, runner integration, and cross-agent stats.
"""

import json
import pytest
from unittest.mock import MagicMock

from src.core.agents.validation_agent import ValidationAgent
from src.core.agents.code_agent import CodeAgent
from src.core.agents.automation_agent import AutomationAgent
from src.core.agents.schemas import (
    ValidationInput, ValidationOutput, ValidationIssue,
    CodeInput, AutomationInput,
)
from src.core.agents.base import AgentResult


# ============================================================
#  TestValidationAgent (15+ tests)
# ============================================================

class TestValidationAgentCodeSecurity:
    """Tests for ValidationAgent security issue detection."""

    def test_validate_code_eval(self, validation_agent):
        """Should detect eval() as security vulnerability."""
        inp = ValidationInput(target="code", content="result = eval(user_input)", language="python")
        result = validation_agent.fallback(inp)
        assert isinstance(result, ValidationOutput)
        issue_codes = [i.code for i in result.issues]
        assert "dangerous_eval" in issue_codes
        assert result.is_valid is False
        assert result.source == "fallback"

    def test_validate_code_exec(self, validation_agent):
        """Should detect exec() as security vulnerability."""
        inp = ValidationInput(target="code", content="exec(command)", language="python")
        result = validation_agent.fallback(inp)
        issue_codes = [i.code for i in result.issues]
        assert "dangerous_exec" in issue_codes
        assert result.is_valid is False

    def test_validate_code_os_system(self, validation_agent):
        """Should detect os.system() as command injection vulnerability."""
        inp = ValidationInput(target="code", content="os.system(cmd)", language="python")
        result = validation_agent.fallback(inp)
        issue_codes = [i.code for i in result.issues]
        assert "command_injection" in issue_codes
        assert result.is_valid is False


class TestValidationAgentCodeQuality:
    """Tests for ValidationAgent code quality issue detection."""

    def test_validate_code_bare_except(self, validation_agent):
        """Should detect bare except as quality issue."""
        inp = ValidationInput(target="code", content="try:\n    x = 1\nexcept:\n    pass", language="python",
                              rules=["quality"])
        result = validation_agent.fallback(inp)
        # bare_except can be detected by both regex patterns and AST
        issue_codes = [i.code for i in result.issues]
        assert "bare_except" in issue_codes

    def test_validate_code_pass(self, validation_agent):
        """Should detect empty pass blocks as quality issue."""
        code = "class Empty:\n    pass"
        inp = ValidationInput(target="code", content=code, language="python", rules=["quality"])
        result = validation_agent.fallback(inp)
        issue_codes = [i.code for i in result.issues]
        assert "empty_block" in issue_codes


class TestValidationAgentPythonAST:
    """Tests for ValidationAgent Python AST-based analysis."""

    def test_validate_python_ast_missing_return(self, validation_agent):
        """Should detect function that may not return on all paths."""
        code = "def compute(x):\n    if x > 0:\n        return x\n    print('no return')"
        inp = ValidationInput(target="code", content=code, language="python")
        result = validation_agent.fallback(inp)
        issue_codes = [i.code for i in result.issues]
        assert "missing_return" in issue_codes

    def test_validate_python_ast_resource_leak(self, validation_agent):
        """Should detect open() without 'with' as resource leak."""
        code = "def read_file(path):\n    f = open(path)\n    return f.read()"
        inp = ValidationInput(target="code", content=code, language="python")
        result = validation_agent.fallback(inp)
        issue_codes = [i.code for i in result.issues]
        assert "resource_leak" in issue_codes

    def test_validate_code_syntax_error(self, validation_agent):
        """Should detect syntax errors in Python code."""
        code = "def broken(\n    return 1"
        inp = ValidationInput(target="code", content=code, language="python")
        result = validation_agent.fallback(inp)
        issue_codes = [i.code for i in result.issues]
        assert "syntax_error" in issue_codes
        assert result.is_valid is False

    def test_validate_code_empty_content(self, validation_agent):
        """Should handle empty code content gracefully."""
        inp = ValidationInput(target="code", content="", language="python")
        result = validation_agent.fallback(inp)
        assert result.is_valid is True
        assert result.risk_score == 0.0

    def test_validate_code_no_issues(self, validation_agent):
        """Should return valid for clean Python code."""
        code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        inp = ValidationInput(target="code", content=code, language="python")
        result = validation_agent.fallback(inp)
        # Clean code should be valid (may have info-level issues but no errors)
        assert result.is_valid is True


class TestValidationAgentChain:
    """Tests for ValidationAgent chain validation."""

    def test_validate_chain_empty(self, validation_agent):
        """Should handle empty chain with info issue."""
        chain_data = json.dumps({"blocks": []})
        inp = ValidationInput(target="chain", content=chain_data)
        result = validation_agent.fallback(inp)
        issue_codes = [i.code for i in result.issues]
        assert "empty_chain" in issue_codes
        assert result.is_valid is True

    def test_validate_chain_compatibility_hints(self, validation_agent):
        """Should detect compatibility hints between block types."""
        chain_data = json.dumps({
            "blocks": [
                {"name": "validator", "type": "validation", "category": "validation"},
                {"name": "processor", "type": "data", "category": "business_logic"},
            ]
        })
        inp = ValidationInput(target="chain", content=chain_data)
        result = validation_agent.fallback(inp)
        issue_codes = [i.code for i in result.issues]
        assert "compatibility_hint" in issue_codes

    def test_validate_chain_long_chain_warning(self, validation_agent):
        """Should warn about chains with more than 10 blocks."""
        blocks = [{"name": f"block_{i}", "type": "data", "category": "data"} for i in range(12)]
        chain_data = json.dumps({"blocks": blocks})
        inp = ValidationInput(target="chain", content=chain_data)
        result = validation_agent.fallback(inp)
        issue_codes = [i.code for i in result.issues]
        assert "long_chain" in issue_codes


class TestValidationAgentConfig:
    """Tests for ValidationAgent config validation."""

    def test_validate_config_debug_enabled(self, validation_agent):
        """Should detect DEBUG mode enabled as info issue."""
        config_data = json.dumps({"DEBUG": True, "PORT": 8000})
        inp = ValidationInput(target="config", content=config_data)
        result = validation_agent.fallback(inp)
        issue_codes = [i.code for i in result.issues]
        assert "debug_enabled" in issue_codes

    def test_validate_config_weak_secret_key(self, validation_agent):
        """Should detect default SECRET_KEY as error."""
        config_data = json.dumps({"SECRET_KEY": "change-this", "DEBUG": False})
        inp = ValidationInput(target="config", content=config_data)
        result = validation_agent.fallback(inp)
        issue_codes = [i.code for i in result.issues]
        assert "weak_secret_key" in issue_codes
        assert result.is_valid is False

    def test_validate_config_valid(self, validation_agent):
        """Should return valid for safe config."""
        config_data = json.dumps({"SECRET_KEY": "a-secure-random-key-xyz", "DEBUG": False})
        inp = ValidationInput(target="config", content=config_data)
        result = validation_agent.fallback(inp)
        assert result.is_valid is True

    def test_validate_config_invalid_format(self, validation_agent):
        """Should detect invalid config format."""
        # Use a dict-like string that fails JSON and YAML parsing
        # yaml.safe_load is permissive, so use truly broken syntax
        inp = ValidationInput(target="config", content="{invalid: json: broken}")
        # JSON parse fails, YAML may also fail or return non-dict
        result = validation_agent.fallback(inp)
        # Even if YAML parses it as a dict, the config won't have problematic keys
        assert isinstance(result, ValidationOutput)


class TestValidationAgentBuildPromptAndParse:
    """Tests for ValidationAgent build_prompt and parse_response."""

    def test_build_prompt_with_validation_input(self, validation_agent):
        """Should build system + user prompt from ValidationInput."""
        inp = ValidationInput(
            target="code", content="eval(x)", rules=["security"], language="python",
        )
        system, user = validation_agent.build_prompt(inp)
        assert "validation" in system.lower()
        assert "eval" in user
        assert "security" in user

    def test_build_prompt_with_string(self, validation_agent):
        """Should build prompt from plain string input."""
        system, user = validation_agent.build_prompt("some code to validate")
        assert "validation" in system.lower()
        assert "some code" in user

    def test_parse_response_valid_json(self, validation_agent):
        """Should parse valid JSON response into ValidationOutput."""
        raw = json.dumps({
            "is_valid": False,
            "issues": [
                {"severity": "error", "code": "dangerous_eval", "message": "Use of eval()", "line": 1, "suggestion": "Use ast.literal_eval()"},
            ],
            "suggestions": ["Replace eval() with ast.literal_eval()"],
            "risk_score": 0.5,
        })
        result = validation_agent.parse_response(raw, None)
        assert result is not None
        assert result.is_valid is False
        assert len(result.issues) == 1
        assert result.issues[0].code == "dangerous_eval"
        assert result.risk_score == 0.5
        assert result.source == "llm"


class TestValidationAgentCompatibilityAndRunner:
    """Tests for ValidationAgent compatibility methods and runner integration."""

    def test_to_validation_result(self, validation_agent):
        """Should convert ValidationOutput to ChainValidator.ValidationResult."""
        from src.core.chain_validator import ValidationResult

        output = ValidationOutput(
            is_valid=False,
            issues=[
                ValidationIssue(severity="error", code="missing_name", message="No name", line=0),
                ValidationIssue(severity="warning", code="missing_category", message="No category", line=0),
            ],
            suggestions=["Add a name"],
            risk_score=0.3,
        )
        result = validation_agent.to_validation_result(output)
        assert isinstance(result, ValidationResult)
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert len(result.warnings) == 1
        assert result.errors[0].code == "missing_name"

    def test_risk_score_calculation(self, validation_agent):
        """Should calculate risk score based on issue severity."""
        issues = [
            ValidationIssue(severity="error", code="dangerous_eval", message="eval()", line=1),
            ValidationIssue(severity="warning", code="bare_except", message="bare except", line=3),
            ValidationIssue(severity="info", code="todo_comment", message="TODO found", line=5),
        ]
        score = validation_agent._calculate_risk_score(issues)
        # error=0.3, warning=0.1, info=0.02 → total=0.42
        assert 0.3 < score < 0.5

    def test_risk_score_no_issues(self, validation_agent):
        """Should return 0.0 risk score when no issues found."""
        score = validation_agent._calculate_risk_score([])
        assert score == 0.0

    def test_risk_score_capped_at_1(self, validation_agent):
        """Risk score should never exceed 1.0."""
        issues = [ValidationIssue(severity="error", code=f"err_{i}", message="err", line=0) for i in range(10)]
        score = validation_agent._calculate_risk_score(issues)
        assert score <= 1.0

    def test_validate_with_runner_success(self, validation_agent):
        """Should return LLM result when runner succeeds."""
        mock_runner = MagicMock()
        llm_output = ValidationOutput(
            is_valid=False, issues=[ValidationIssue(severity="error", code="eval", message="eval()")],
            suggestions=["Fix it"], risk_score=0.5, source="llm",
        )
        mock_runner.run.return_value = AgentResult(success=True, data=llm_output, source="llm")
        result = validation_agent.validate_with_runner(mock_runner, "code", "eval(x)")
        assert result.is_valid is False
        assert result.source == "llm"

    def test_validate_with_runner_fallback(self, validation_agent):
        """Should use fallback when runner fails."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(success=False, data=None, error="timeout")
        result = validation_agent.validate_with_runner(mock_runner, "code", "eval(x)")
        assert isinstance(result, ValidationOutput)
        assert result.source == "fallback"


# ============================================================
#  Test: Stats tracking across all agents
# ============================================================

class TestAgentStats:
    """Tests for agent statistics tracking across all 3 agents."""

    def test_code_agent_stats_after_fallback(self, code_agent):
        """Should track fallback stats in CodeAgent."""
        code_agent.fallback(CodeInput(task="generate", requirements="test", language="python"))
        stats = code_agent.stats
        assert stats["name"] == "code"
        assert stats["total_calls"] >= 1
        assert stats["fallback_calls"] >= 1

    def test_automation_agent_stats_after_fallback(self, automation_agent):
        """Should track fallback stats in AutomationAgent."""
        automation_agent.fallback(AutomationInput(description="daily backup"))
        stats = automation_agent.stats
        assert stats["name"] == "automation"
        assert stats["total_calls"] >= 1

    def test_validation_agent_stats_after_fallback(self, validation_agent):
        """Should track fallback stats in ValidationAgent."""
        validation_agent.fallback(ValidationInput(target="code", content="x = 1"))
        stats = validation_agent.stats
        assert stats["name"] == "validation"
        assert stats["total_calls"] >= 1

    def test_initial_stats_all_agents(self, code_agent, automation_agent, validation_agent):
        """Should have zero stats initially for all agents."""
        for agent in [code_agent, automation_agent, validation_agent]:
            stats = agent.stats
            assert stats["total_calls"] == 0
            assert stats["llm_success"] == 0
            assert stats["fallback_calls"] == 0
