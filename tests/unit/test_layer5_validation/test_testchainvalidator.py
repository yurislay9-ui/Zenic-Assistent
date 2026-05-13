"""
Tests for Layer 5: Validation & Security agents (A23-A28).

All 6 agents tested:
  - A23 SecurityScanner
  - A24 SyntaxValidator
  - A25 ChainValidator
  - A26 ConfigValidator
  - A27 RiskCalculator
  - A28 FixSuggester
"""

import json
import pytest

from src.core.agents_v2.validation import (
    SecurityScanner,
    SyntaxValidator,
    ChainValidator,
    ConfigValidator,
    RiskCalculator,
    FixSuggester,
)
from src.core.agents_v2.schemas import (
    SecurityResult,
    SyntaxResult,
    ChainResult,
    ConfigResult,
    RiskResult,
    FixSuggestions,
    ValidationIssue,
)


# ═══════════════════════════════════════════════════════════
# A23 SecurityScanner Tests
# ═══════════════════════════════════════════════════════════



class TestChainValidator:
    """A25: Validate logic chain compatibility and completeness."""

    def setup_method(self):
        self.validator = ChainValidator()

    def test_empty_chain_is_valid(self):
        """Empty chain should be valid with missing=['blocks']."""
        result = self.validator.execute({"chain": {"blocks": []}})
        assert isinstance(result, ChainResult)
        assert result.valid is True
        assert "blocks" in result.missing

    def test_valid_simple_chain(self):
        """Simple valid chain with context should pass cleanly."""
        chain = {
            "blocks": [
                {"name": "fetch_data", "category": "data", "outputs": ["records"]},
                {"name": "validate_data", "category": "validation", "inputs": ["records"]},
            ]
        }
        result = self.validator.execute({"chain": chain, "context": {"db": True}})
        assert result.valid is True
        # No type mismatches or critical issues
        assert not any("Type mismatch" in i or "CRITICAL" in i for i in result.incompatibilities)

    def test_missing_block_name_warning(self):
        """Block without name should produce incompatibility."""
        chain = {"blocks": [{"category": "data"}]}
        result = self.validator.execute({"chain": chain})
        assert any("no name" in i for i in result.incompatibilities)

    def test_type_mismatch_detected(self):
        """Type incompatibility between blocks should be detected."""
        chain = {
            "blocks": [
                {"name": "step1", "category": "data", "outputs": [{"type": "records"}]},
                {"name": "step2", "category": "business_logic", "inputs": [{"type": "html"}]},
            ]
        }
        result = self.validator.execute({"chain": chain})
        assert any("Type mismatch" in i for i in result.incompatibilities)

    def test_type_any_is_compatible(self):
        """Type 'any' should be compatible with everything."""
        chain = {
            "blocks": [
                {"name": "step1", "category": "data", "outputs": [{"type": "records"}]},
                {"name": "step2", "category": "validation", "inputs": [{"type": "any"}]},
            ]
        }
        result = self.validator.execute({"chain": chain})
        assert not any("Type mismatch" in i for i in result.incompatibilities)

    def test_category_compatibility_warning(self):
        """Incompatible category transitions should produce hints."""
        chain = {
            "blocks": [
                {"name": "validate", "category": "validation"},
                {"name": "logic", "category": "business_logic"},
            ]
        }
        result = self.validator.execute({"chain": chain})
        assert any("Category hint" in i for i in result.incompatibilities)

    def test_auth_block_needs_db_context(self):
        """Auth block without db in context should warn."""
        chain = {"blocks": [{"name": "auth_step", "category": "auth"}]}
        result = self.validator.execute({"chain": chain, "context": {}})
        assert any("auth" in i.lower() and "db" in i for i in result.incompatibilities)

    def test_auth_block_with_db_context_ok(self):
        """Auth block with db in context should not warn."""
        chain = {"blocks": [{"name": "auth_step", "category": "auth"}]}
        result = self.validator.execute({"chain": chain, "context": {"db": True}})
        assert not any("auth" in i.lower() and "db" in i for i in result.incompatibilities)

    def test_strict_mode_long_chain(self):
        """Strict mode: chain >10 blocks should warn."""
        blocks = [{"name": f"step_{i}", "category": "data"} for i in range(12)]
        chain = {"blocks": blocks}
        result = self.validator.execute({"chain": chain, "strict": True})
        assert any("12 blocks" in i for i in result.incompatibilities)

    def test_strict_mode_duplicate_names(self):
        """Strict mode: duplicate block names should warn."""
        chain = {
            "blocks": [
                {"name": "process", "category": "data"},
                {"name": "process", "category": "data"},
            ]
        }
        result = self.validator.execute({"chain": chain, "strict": True})
        assert any("Duplicate" in i for i in result.incompatibilities)

    def test_strict_mode_validation_after_logic(self):
        """Strict mode: validation after business_logic should warn."""
        chain = {
            "blocks": [
                {"name": "logic", "category": "business_logic"},
                {"name": "validate", "category": "validation"},
            ]
        }
        result = self.validator.execute({"chain": chain, "strict": True})
        assert any("Validation after" in i for i in result.incompatibilities)

    def test_json_string_chain(self):
        """JSON string chain should be parsed correctly."""
        chain_json = json.dumps({
            "blocks": [{"name": "step1", "category": "data"}]
        })
        result = self.validator.execute({"chain": chain_json})
        assert result.valid is True

    def test_missing_auth_block(self):
        """auth_required context without auth block should report missing."""
        chain = {"blocks": [{"name": "data_step", "category": "data"}]}
        result = self.validator.execute({
            "chain": chain,
            "context": {"auth_required": True},
        })
        assert "auth_block" in result.missing

    def test_object_blocks_with_attributes(self):
        """Blocks as objects with attributes should work."""
        class MockBlock:
            def __init__(self, name, category):
                self.name = name
                self.category = category
                self.outputs = []
                self.inputs = []
                self.execute = lambda data: data  # Has execute method

        chain = {"blocks": [MockBlock("step1", "data")]}
        result = self.validator.execute({"chain": chain, "context": {"db": True}})
        assert result.valid is True

    def test_fallback_returns_valid(self):
        """Fallback should return valid=True."""
        result = self.validator.fallback(None)
        assert result.valid is True
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A26 ConfigValidator Tests
# ═══════════════════════════════════════════════════════════

