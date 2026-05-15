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

from src.core.agents.validation import (
    SecurityScanner,
    SyntaxValidator,
    ChainValidator,
    ConfigValidator,
    RiskCalculator,
    FixSuggester,
)
from src.core.agents.schemas import (
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



class TestValidationPipeline:
    """End-to-end validation pipeline through all Layer 5 agents."""

    def test_clean_code_passes_all(self):
        """Clean code should pass all validation layers."""
        code = "import logging\n\ndef process(data: dict) -> dict:\n    logger = logging.getLogger()\n    if not data:\n        raise ValueError('data required')\n    try:\n        result = {'processed': True}\n    except Exception as e:\n        logger.error(str(e))\n        raise\n    return result\n"

        # Step 1: Security scan
        scanner = SecurityScanner()
        sec_result = scanner.execute({"code": code})
        assert sec_result.safe is True

        # Step 2: Syntax validation
        validator = SyntaxValidator()
        syn_result = validator.execute({"code": code, "language": "python"})
        assert syn_result.valid is True

        # Step 3: Risk calculation
        calculator = RiskCalculator()
        risk_result = calculator.execute({
            "security_result": sec_result,
            "syntax_result": syn_result,
        })
        assert risk_result.level == "low"

        # Step 4: Fix suggestions (should be empty)
        suggester = FixSuggester()
        all_issues = sec_result.threats + syn_result.errors
        fix_result = suggester.execute(all_issues)
        assert len(fix_result.suggestions) == 0

    def test_dangerous_code_caught(self):
        """Dangerous code should be caught at security scan."""
        code = "eval(user_input)\nos.system('rm -rf /')\npickle.loads(data)"

        scanner = SecurityScanner()
        sec_result = scanner.execute({"code": code})
        assert sec_result.safe is False

        # Should have multiple threats
        assert len(sec_result.threats) >= 2

        # Risk should be elevated
        calculator = RiskCalculator()
        risk_result = calculator.execute({
            "security_result": sec_result,
            "syntax_result": SyntaxResult(valid=True),
        })
        assert risk_result.level in ("medium", "high", "critical")

        # Should get fix suggestions
        suggester = FixSuggester()
        fix_result = suggester.execute(sec_result.threats)
        assert len(fix_result.suggestions) >= 2

    def test_chain_and_config_validation(self):
        """Chain + Config validation together."""
        # Validate a chain
        chain_validator = ChainValidator()
        chain_result = chain_validator.execute({
            "chain": {
                "blocks": [
                    {"name": "fetch", "category": "data"},
                    {"name": "validate", "category": "validation"},
                ]
            }
        })
        assert chain_result.valid is True

        # Validate config
        config_validator = ConfigValidator()
        config_result = config_validator.execute({
            "config": {"host": "localhost", "port": 5432, "name": "mydb"},
            "config_type": "database",
        })
        assert config_result.valid is True
