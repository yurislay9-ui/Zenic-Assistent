"""
Tests for ValidationAgent chain validation, config validation,
risk score calculation, and fix suggestions.
"""

import pytest

from src.core.agents.schemas import ValidationInput


# ============================================================
#  Test: Chain Validation
# ============================================================

class TestValidationChain:
    """Tests for chain/logic block validation."""

    def test_empty_chain(self, agent):
        """Should handle empty chain gracefully."""
        result = agent.fallback(ValidationInput(
            target="chain",
            content='{"blocks": []}',
        ))
        assert result.is_valid is True
        codes = [i.code for i in result.issues]
        assert "empty_chain" in codes

    def test_valid_chain(self, agent):
        """Should validate a valid chain."""
        chain = {
            "blocks": [
                {"name": "fetch_data", "category": "data"},
                {"name": "validate_data", "category": "validation"},
            ]
        }
        result = agent.fallback(ValidationInput(
            target="chain",
            content=chain,
        ))
        assert result.is_valid is True

    def test_missing_block_name(self, agent):
        """Should warn about blocks without names."""
        chain = {"blocks": [{}]}
        result = agent.fallback(ValidationInput(
            target="chain",
            content=chain,
        ))
        codes = [i.code for i in result.issues]
        assert "missing_name" in codes

    def test_long_chain_warning(self, agent):
        """Should warn about chains with >10 blocks."""
        blocks = [{"name": f"block_{i}", "category": "data"} for i in range(12)]
        chain = {"blocks": blocks}
        result = agent.fallback(ValidationInput(
            target="chain",
            content=chain,
        ))
        codes = [i.code for i in result.issues]
        assert "long_chain" in codes


# ============================================================
#  Test: Config Validation
# ============================================================

class TestValidationConfig:
    """Tests for configuration validation."""

    def test_debug_enabled(self, agent):
        """Should warn about DEBUG mode enabled."""
        config = {"DEBUG": True}
        result = agent.fallback(ValidationInput(
            target="config",
            content=config,
        ))
        codes = [i.code for i in result.issues]
        assert "debug_enabled" in codes

    def test_weak_secret_key(self, agent):
        """Should detect default/weak SECRET_KEY."""
        config = {"SECRET_KEY": "change-this"}
        result = agent.fallback(ValidationInput(
            target="config",
            content=config,
        ))
        assert result.is_valid is False
        codes = [i.code for i in result.issues]
        assert "weak_secret_key" in codes

    def test_valid_config(self, agent):
        """Should pass a valid config."""
        config = {"SECRET_KEY": "a1b2c3d4e5f6g7h8i9j0", "DEBUG": False}
        result = agent.fallback(ValidationInput(
            target="config",
            content=config,
        ))
        assert result.is_valid is True

    def test_invalid_json_string(self, agent):
        """Should detect invalid JSON config string."""
        result = agent.fallback(ValidationInput(
            target="config",
            content="{not valid json at all !@#}",
        ))
        assert isinstance(result.is_valid, bool)
        assert isinstance(result.risk_score, float)


# ============================================================
#  Test: Risk Score Calculation
# ============================================================

class TestValidationRiskScore:
    """Tests for risk score calculation."""

    def test_no_issues_zero_risk(self, agent):
        """Should have 0 risk score when no issues."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="x = 1",
            language="python",
        ))
        assert result.risk_score == 0.0

    def test_error_issues_increase_risk(self, agent):
        """Should have higher risk score with error-level issues."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="eval('dangerous')",
            language="python",
        ))
        assert result.risk_score > 0.0

    def test_risk_score_capped_at_1(self, agent):
        """Risk score should never exceed 1.0."""
        code = "eval('a')\nexec('b')\nos.system('c')\npickle.loads(d)\n"
        result = agent.fallback(ValidationInput(
            target="code",
            content=code,
            language="python",
        ))
        assert result.risk_score <= 1.0


# ============================================================
#  Test: Fix Suggestions
# ============================================================

class TestValidationFixSuggestions:
    """Tests for fix suggestion generation."""

    def test_suggestion_for_eval(self, agent):
        """Should suggest replacing eval() with ast.literal_eval()."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="eval(user_data)",
            language="python",
        ))
        suggestions = result.suggestions
        assert any("literal_eval" in s or "eval" in s for s in suggestions)

    def test_suggestion_for_pickle(self, agent):
        """Should suggest json instead of pickle."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="pickle.loads(data)",
            language="python",
        ))
        suggestions = result.suggestions
        assert any("json" in s or "pickle" in s for s in suggestions)
