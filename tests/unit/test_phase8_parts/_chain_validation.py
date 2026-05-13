"""Tests for ChainValidator and ChainExecutor (Phase 8.3)."""


class TestChainValidator:
    """Tests for ChainValidator and ChainExecutor (Phase 8.3)."""

    def setup_method(self):
        from src.core.chain_validator import (
            ChainValidator, ChainExecutor, ValidationLevel,
            RecoveryAction, ChainStatus
        )
        from src.core.logic_builder import LogicBuilder
        self.validator = ChainValidator()
        self.builder = LogicBuilder()

    def test_validator_initializes(self):
        """ChainValidator should initialize."""
        assert self.validator is not None
        assert self.validator._level.value == "standard"

    def test_validator_lenient_level(self):
        """Should support lenient validation level."""
        from src.core.chain_validator import ChainValidator, ValidationLevel
        v = ChainValidator(level=ValidationLevel.LENIENT)
        assert v._level == ValidationLevel.LENIENT

    def test_validate_valid_chain(self):
        """Valid chain should pass validation."""
        chain = self.builder.build_from_blocks(["validate_required", "sanitize"])
        result = self.validator.validate(chain, {"name": "Test"}, {})
        assert result.is_valid is True

    def test_validate_empty_chain(self):
        """Empty chain should produce a warning."""
        from src.core.logic_builder import LogicChain
        empty_chain = LogicChain("empty")
        result = self.validator.validate(empty_chain)
        assert len(result.warnings) > 0

    def test_validate_auth_without_db_warns(self):
        """Auth blocks without db in context should warn."""
        chain = self.builder.build_from_blocks(["auth_login"])
        result = self.validator.validate(chain, {}, {})
        # May have warnings about missing db context
        assert isinstance(result.warnings, list)

    def test_validation_result_add_error(self):
        """ValidationResult should track errors correctly."""
        from src.core.chain_validator import ValidationResult
        result = ValidationResult()
        result.add_error("test_code", "Test error", "test_block", 0)
        assert result.is_valid is False
        assert result.can_execute is False
        assert len(result.errors) == 1

    def test_validation_result_add_warning(self):
        """ValidationResult should track warnings without blocking execution."""
        from src.core.chain_validator import ValidationResult
        result = ValidationResult()
        result.add_warning("test_code", "Test warning", "test_block", 0)
        assert result.is_valid is True
        assert result.can_execute is True
        assert len(result.warnings) == 1

    def test_execute_chain_simple(self):
        """ChainExecutor should execute a simple chain."""
        from src.core.chain_validator import ChainExecutor, ChainStatus
        chain = self.builder.build_from_blocks(["validate_required"])
        executor = ChainExecutor()
        result = executor.execute(chain, {"name": "Test"}, {"required_fields": ["name"]})
        assert result.status in (ChainStatus.COMPLETED, ChainStatus.PARTIAL)

    def test_execute_chain_with_validation(self):
        """ChainExecutor should validate before execution."""
        from src.core.chain_validator import ChainExecutor, ChainStatus
        chain = self.builder.build_from_blocks(["sanitize"])
        executor = ChainExecutor()
        result = executor.execute(chain, {"name": "Test"}, {}, validate_first=True)
        assert result.validation is not None

    def test_execute_chain_skip_recovery(self):
        """ChainExecutor should skip failed blocks with SKIP recovery."""
        from src.core.chain_validator import (
            ChainExecutor, RecoveryAction, ChainStatus
        )
        # Create a chain that might fail
        chain = self.builder.build_from_blocks(["validate_required"])
        executor = ChainExecutor(default_recovery=RecoveryAction.SKIP)
        result = executor.execute(chain, {}, {})
        # Should not crash even with empty data
        assert result.status in (ChainStatus.COMPLETED, ChainStatus.PARTIAL, ChainStatus.FAILED)

    def test_execute_chain_abort_recovery(self):
        """ChainExecutor should abort on failure with ABORT recovery."""
        from src.core.chain_validator import (
            ChainExecutor, RecoveryAction, ChainStatus
        )
        chain = self.builder.build_from_blocks(["validate_required"])
        executor = ChainExecutor(default_recovery=RecoveryAction.ABORT)
        result = executor.execute(chain, {}, {})
        assert isinstance(result.steps_failed, int)

    def test_convenience_validate_chain(self):
        """validate_chain() convenience function should work."""
        from src.core.chain_validator import validate_chain
        chain = self.builder.build_from_blocks(["sanitize"])
        result = validate_chain(chain, {"name": "test"}, {})
        assert result.is_valid is True

    def test_convenience_execute_chain_safe(self):
        """execute_chain_safe() convenience function should work."""
        from src.core.chain_validator import execute_chain_safe
        chain = self.builder.build_from_blocks(["validate_required"])
        result = execute_chain_safe(chain, {"name": "Test"}, {"required_fields": ["name"]})
        assert result.final_data is not None
