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



class TestSecurityScanner:
    """A23: Scan for dangerous patterns."""

    def setup_method(self):
        self.scanner = SecurityScanner()

    def test_safe_code_passes(self):
        """Clean code should be safe=True with risk_score=0.0."""
        result = self.scanner.execute({"code": "x = 1 + 2\nprint(x)"})
        assert isinstance(result, SecurityResult)
        assert result.safe is True
        assert result.risk_score == 0.0
        assert len(result.threats) == 0

    def test_eval_detected(self):
        """eval() should be detected as a threat."""
        result = self.scanner.execute({"code": "result = eval(user_input)"})
        assert result.safe is False
        assert any(t.code == "dangerous_eval" for t in result.threats)
        assert result.risk_score > 0

    def test_exec_detected(self):
        """exec() should be detected as a threat."""
        result = self.scanner.execute({"code": "exec(code_string)"})
        assert result.safe is False
        assert any(t.code == "dangerous_exec" for t in result.threats)

    def test_os_system_detected(self):
        """os.system() should be detected."""
        result = self.scanner.execute({"code": "os.system('rm -rf /')"})
        assert result.safe is False
        assert any(t.code == "os_system" for t in result.threats)

    def test_pickle_detected(self):
        """pickle.loads() should be detected."""
        result = self.scanner.execute({"code": "data = pickle.loads(raw)"})
        assert result.safe is False
        assert any(t.code == "pickle_load" for t in result.threats)

    def test_sql_injection_detected(self):
        """SQL injection via f-string should be detected."""
        result = self.scanner.execute({"code": 'f"SELECT * FROM users WHERE id={user_id}"'})
        assert result.safe is False
        assert any(t.code == "sql_injection" for t in result.threats)

    def test_subprocess_shell_detected(self):
        """subprocess with shell=True should be detected."""
        result = self.scanner.execute({"code": "subprocess.run(cmd, shell=True)"})
        assert result.safe is False
        assert any(t.code == "subprocess_shell" for t in result.threats)

    def test_weak_hash_md5_detected(self):
        """hashlib.md5() should be detected."""
        result = self.scanner.execute({"code": "hashlib.md5(data)"})
        assert result.safe is False
        assert any(t.code == "weak_hash_md5" for t in result.threats)

    def test_bare_except_detected(self):
        """Bare except should be detected."""
        result = self.scanner.execute({"code": "try:\n    x = 1\nexcept:\n    pass"})
        assert any(t.code == "bare_except" for t in result.threats)

    def test_safe_patterns_reduce_risk(self):
        """Safe patterns (try/except, logging, type hints) should reduce risk score."""
        dangerous = self.scanner.execute({"code": "eval('1+1')"})
        dangerous_with_safe = self.scanner.execute(
            {"code": "import logging\nlogger = logging.getLogger()\ntry:\n    eval('1+1')\nexcept ValueError:\n    logger.error('bad')"}
        )
        # Both should be unsafe (eval detected), but safe patterns reduce risk
        assert dangerous_with_safe.risk_score <= dangerous.risk_score

    def test_empty_code_is_safe(self):
        """Empty code should default to safe=True."""
        result = self.scanner.execute({"code": ""})
        assert result.safe is True

    def test_string_input_works(self):
        """String input (not dict) should work."""
        result = self.scanner.execute("eval('bad')")
        assert result.safe is False

    def test_fallback_returns_safe(self):
        """Fallback should return safe=False (precaution principle)."""
        result = self.scanner.fallback(None)
        assert result.safe is False
        assert result.risk_score == 1.0
        assert result.source == "fallback"

    def test_multiple_threats_detected(self):
        """Multiple threats in one code block should all be found."""
        code = "eval('x')\nexec('y')\nos.system('ls')"
        result = self.scanner.execute({"code": code})
        assert result.safe is False
        threat_codes = {t.code for t in result.threats}
        assert "dangerous_eval" in threat_codes
        assert "dangerous_exec" in threat_codes
        assert "os_system" in threat_codes

    def test_suggestions_provided(self):
        """Each threat should have a fix suggestion."""
        result = self.scanner.execute({"code": "eval('x')"})
        assert len(result.threats) > 0
        for threat in result.threats:
            assert threat.suggestion != ""


# ═══════════════════════════════════════════════════════════
# A24 SyntaxValidator Tests
# ═══════════════════════════════════════════════════════════

