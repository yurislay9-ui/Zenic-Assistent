"""
ZENIC-AGENTS - ChainValidator Unit Tests

Tests for src/core/chain_validator.py:
  - ChainValidator: validation levels, block checks, compatibility
  - ChainExecutor: execution with recovery strategies, rollback
  - ValidationResult / ChainResult data classes
  - Convenience functions: validate_chain, execute_chain_safe
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from src.core.chain_validator import (
    ChainValidator,
    ChainExecutor,
    ValidationLevel,
    RecoveryAction,
    ChainStatus,
    ValidationResult,
    ValidationError,
    StepResult,
    ChainResult,
    validate_chain,
    execute_chain_safe,
)


# ============================================================
#  HELPER: Mock chain/block objects
# ============================================================

class MockBlock:
    """A mock logic block with configurable behavior."""

    def __init__(self, name="test_block", category="data", outputs=None, inputs=None,
                 execute_result=None, execute_side_effect=None):
        self.name = name
        self.category = category
        self.outputs = outputs or []
        self.inputs = inputs or []
        self._execute_result = execute_result or {"success": True, "data": "processed"}
        self._execute_side_effect = execute_side_effect

    def execute(self, data, context):
        if self._execute_side_effect:
            raise self._execute_side_effect
        return self._execute_result


class MockChain:
    """A mock LogicChain with a list of blocks."""

    def __init__(self, blocks=None):
        self.blocks = blocks or []


# ============================================================
#  VALIDATIONRESULT TESTS
# ============================================================

class TestValidationResult:
    """Tests for ValidationResult data class."""

    def test_initial_state_is_valid(self):
        """New ValidationResult should be valid and executable."""
        result = ValidationResult()
        assert result.is_valid is True
        assert result.can_execute is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_add_error_invalidates(self):
        """Adding an error should invalidate the result."""
        result = ValidationResult()
        result.add_error("missing_input", "Required input missing")
        assert result.is_valid is False
        assert result.can_execute is False
        assert len(result.errors) == 1

    def test_add_warning_does_not_invalidate(self):
        """Adding a warning should NOT invalidate the result."""
        result = ValidationResult()
        result.add_warning("missing_category", "No category set")
        assert result.is_valid is True
        assert result.can_execute is True
        assert len(result.warnings) == 1

    def test_error_and_warning_coexist(self):
        """Errors and warnings should be tracked independently."""
        result = ValidationResult()
        result.add_error("err1", "Error 1")
        result.add_warning("warn1", "Warning 1")
        assert len(result.errors) == 1
        assert len(result.warnings) == 1
        assert result.is_valid is False


# ============================================================
#  CHAIN VALIDATOR TESTS
# ============================================================

class TestChainValidator:
    """Tests for ChainValidator."""

    def setup_method(self):
        self.validator = ChainValidator(level=ValidationLevel.STANDARD)

    def test_initializes_with_level(self):
        """Should initialize with given validation level."""
        v = ChainValidator(level=ValidationLevel.STRICT)
        assert v._level == ValidationLevel.STRICT

    def test_empty_chain_warns(self):
        """Empty chain should produce a warning."""
        chain = MockChain([])
        result = self.validator.validate(chain)
        assert len(result.warnings) > 0
        assert any(w.code == "empty_chain" for w in result.warnings)

    def test_valid_chain_passes(self):
        """Valid chain with good blocks should pass."""
        blocks = [
            MockBlock(name="step1", category="data"),
            MockBlock(name="step2", category="validation"),
        ]
        chain = MockChain(blocks)
        result = self.validator.validate(chain, {}, {"db": "test"})
        assert result.is_valid is True

    def test_block_without_name_errors(self):
        """Block without a name should produce an error."""
        nameless = MockBlock(name="", category="data")
        # Remove name attribute
        del nameless.name
        chain = MockChain([nameless])
        result = self.validator.validate(chain)
        assert result.is_valid is False
        assert any(e.code == "missing_name" for e in result.errors)

    def test_block_without_execute_errors(self):
        """Block without execute method should produce an error."""
        class NoExecute:
            name = "broken"
            category = "data"
        chain = MockChain([NoExecute()])
        result = self.validator.validate(chain)
        assert result.is_valid is False
        assert any(e.code == "missing_execute" for e in result.errors)

    def test_auth_block_without_db_warns(self):
        """Auth block without db in context should produce a warning."""
        block = MockBlock(name="login", category="auth")
        chain = MockChain([block])
        result = self.validator.validate(chain, {}, {})
        assert any(w.code == "auth_no_db" for w in result.warnings)

    def test_data_block_without_db_warns(self):
        """Data block without db in context should produce a warning."""
        block = MockBlock(name="query", category="data")
        chain = MockChain([block])
        result = self.validator.validate(chain, {}, {})
        assert any(w.code == "data_no_db" for w in result.warnings)

    def test_lenient_level_skips_compatibility(self):
        """Lenient level should skip compatibility checks."""
        v = ChainValidator(level=ValidationLevel.LENIENT)
        # Two blocks with mismatched outputs/inputs
        blocks = [
            MockBlock(name="a", category="data", outputs=["x"]),
            MockBlock(name="b", category="validation", inputs=["y"]),
        ]
        chain = MockChain(blocks)
        result = v.validate(chain)
        # Lenient should not add compatibility issues
        assert result.is_valid is True

    def test_strict_level_checks_long_chain(self):
        """Strict level should warn about chains longer than 10 blocks."""
        v = ChainValidator(level=ValidationLevel.STRICT)
        blocks = [MockBlock(name=f"step_{i}", category="data") for i in range(12)]
        chain = MockChain(blocks)
        result = v.validate(chain)
        assert any(w.code == "long_chain" for w in result.warnings)

    def test_strict_level_checks_duplicate_blocks(self):
        """Strict level should warn about duplicate block names."""
        v = ChainValidator(level=ValidationLevel.STRICT)
        blocks = [
            MockBlock(name="duplicate", category="data"),
            MockBlock(name="duplicate", category="data"),
        ]
        chain = MockChain(blocks)
        result = v.validate(chain)
        assert any(w.code == "duplicate_block" for w in result.warnings)


# ============================================================
#  CHAIN EXECUTOR TESTS
# ============================================================

class TestChainExecutor:
    """Tests for ChainExecutor."""

    def setup_method(self):
        self.executor = ChainExecutor(
            validator=ChainValidator(level=ValidationLevel.STANDARD),
            default_recovery=RecoveryAction.ABORT,
            max_retries=0,
        )

    def test_simple_execution(self):
        """Should execute a simple chain and return COMPLETED."""
        blocks = [
            MockBlock(name="step1", execute_result={"success": True, "result": "ok"}),
        ]
        chain = MockChain(blocks)
        result = self.executor.execute(chain, {}, {}, validate_first=False)
        assert result.status == ChainStatus.COMPLETED
        assert result.steps_completed == 1

    def test_failed_step_abort(self):
        """Should abort on failure with ABORT recovery."""
        blocks = [
            MockBlock(name="fail_step", execute_result={"success": False, "error": "bad"}),
        ]
        executor = ChainExecutor(default_recovery=RecoveryAction.ABORT, max_retries=0)
        chain = MockChain(blocks)
        result = executor.execute(chain, {}, {}, validate_first=False)
        assert result.status == ChainStatus.FAILED
        assert result.steps_failed == 1

    def test_skip_recovery(self):
        """Should skip failed blocks with SKIP recovery."""
        blocks = [
            MockBlock(name="fail", execute_result={"success": False, "error": "bad"}),
            MockBlock(name="ok", execute_result={"success": True, "data": "ok"}),
        ]
        executor = ChainExecutor(default_recovery=RecoveryAction.SKIP, max_retries=0)
        chain = MockChain(blocks)
        result = executor.execute(chain, {}, {}, validate_first=False)
        assert result.steps_skipped >= 1
        assert result.steps_completed >= 1

    def test_fallback_recovery(self):
        """Should use fallback value with FALLBACK recovery."""
        blocks = [
            MockBlock(name="fail", execute_result={"success": False, "error": "bad"}),
        ]
        executor = ChainExecutor(default_recovery=RecoveryAction.FALLBACK, max_retries=0)
        executor.set_recovery("fail", RecoveryAction.FALLBACK, {"fallback_key": "fallback_val"})
        chain = MockChain(blocks)
        result = executor.execute(chain, {}, {}, validate_first=False)
        assert result.steps_completed >= 1
        assert "fallback_key" in result.final_data

    def test_rollback_recovery(self):
        """Should rollback to last snapshot with ROLLBACK recovery."""
        blocks = [
            MockBlock(name="ok", execute_result={"success": True, "key1": "val1"}),
            MockBlock(name="fail", execute_result={"success": False, "error": "bad"}),
        ]
        executor = ChainExecutor(default_recovery=RecoveryAction.ROLLBACK, max_retries=0)
        chain = MockChain(blocks)
        result = executor.execute(chain, {}, {}, validate_first=False)
        assert result.status == ChainStatus.ROLLED_BACK
        assert result.rollback_count >= 1

    def test_exception_in_block(self):
        """Should handle exceptions from block.execute()."""
        blocks = [
            MockBlock(name="crash", execute_side_effect=RuntimeError("boom")),
        ]
        executor = ChainExecutor(default_recovery=RecoveryAction.ABORT, max_retries=0)
        chain = MockChain(blocks)
        result = executor.execute(chain, {}, {}, validate_first=False)
        assert result.status == ChainStatus.FAILED

    def test_validation_blocks_execution(self):
        """Should block execution when validation fails."""
        # Create chain with block missing execute method
        class BadBlock:
            name = "bad"
            category = "data"
        chain = MockChain([BadBlock()])
        executor = ChainExecutor(default_recovery=RecoveryAction.ABORT)
        result = executor.execute(chain, {}, {}, validate_first=True)
        assert result.status == ChainStatus.FAILED
        assert result.validation is not None
        assert result.validation.is_valid is False

    def test_condition_steps_skipped(self):
        """Condition-type steps should be skipped, not executed."""
        blocks = [
            {"type": "condition", "block": MockBlock(name="cond")},
            MockBlock(name="action"),
        ]
        chain = MockChain(blocks)
        result = self.executor.execute(chain, {}, {}, validate_first=False)
        assert result.status == ChainStatus.COMPLETED


# ============================================================
#  CONVENIENCE FUNCTION TESTS
# ============================================================

class TestConvenienceFunctions:
    """Tests for validate_chain() and execute_chain_safe() convenience functions."""

    def test_validate_chain(self):
        """validate_chain should work as a convenience function."""
        blocks = [MockBlock(name="ok", category="data")]
        chain = MockChain(blocks)
        result = validate_chain(chain, {}, {"db": "test"})
        assert result.is_valid is True

    def test_execute_chain_safe(self):
        """execute_chain_safe should execute with SKIP recovery."""
        blocks = [MockBlock(name="ok", execute_result={"success": True})]
        chain = MockChain(blocks)
        result = execute_chain_safe(chain, {}, {})
        assert result.final_data is not None
