"""
Tests for ValidationAgent code security, quality, and Python AST validation.
"""

import pytest

from src.core.agents.schemas import ValidationInput


# ============================================================
#  Test: Code Validation - Security Patterns
# ============================================================

class TestValidationCodeSecurity:
    """Tests for security vulnerability detection in code."""

    def test_detect_eval(self, agent):
        """Should detect dangerous eval() usage."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="result = eval(user_input)",
            language="python",
        ))
        assert result.is_valid is False
        codes = [i.code for i in result.issues]
        assert "dangerous_eval" in codes

    def test_detect_exec(self, agent):
        """Should detect dangerous exec() usage."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="exec('print(1)')",
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "dangerous_exec" in codes

    def test_detect_os_system(self, agent):
        """Should detect os.system() command injection."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="os.system('rm -rf /')",
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "command_injection" in codes

    def test_detect_subprocess_shell_true(self, agent):
        """Should detect subprocess with shell=True."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="subprocess.call(cmd, shell=True)",
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "shell_injection" in codes

    def test_detect_pickle(self, agent):
        """Should detect pickle deserialization."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="data = pickle.loads(raw_bytes)",
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "pickle_deserialization" in codes

    def test_detect_md5(self, agent):
        """Should detect weak MD5 hash."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="hashlib.md5(data)",
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "weak_hash_md5" in codes

    def test_clean_code_passes(self, agent):
        """Should pass clean code with no issues."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="x = 1 + 2\nresult = x * 3",
            language="python",
        ))
        assert result.is_valid is True
        assert result.risk_score == 0.0

    def test_empty_code_passes(self, agent):
        """Should pass empty code."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="",
            language="python",
        ))
        assert result.is_valid is True
        assert result.risk_score == 0.0


# ============================================================
#  Test: Code Validation - Quality Patterns
# ============================================================

class TestValidationCodeQuality:
    """Tests for code quality pattern detection."""

    def test_detect_bare_except(self, agent):
        """Should detect bare except: clause."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="try:\n    x = 1\nexcept:\n    pass",
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "bare_except" in codes

    def test_detect_todo_comment(self, agent):
        """Should detect TODO/FIXME comments."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="# TODO: fix this later\nx = 1",
            language="python",
            rules=["quality"],
        ))
        codes = [i.code for i in result.issues]
        assert "todo_comment" in codes

    def test_detect_print_statement(self, agent):
        """Should detect print() statements."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="print('debug')",
            language="python",
            rules=["quality"],
        ))
        codes = [i.code for i in result.issues]
        assert "print_statement" in codes


# ============================================================
#  Test: Python AST Analysis
# ============================================================

class TestValidationPythonAST:
    """Tests for Python-specific AST analysis."""

    def test_detect_syntax_error(self, agent):
        """Should detect syntax errors in Python code."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="def foo(\n    x = 1",
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "syntax_error" in codes
        assert result.is_valid is False

    def test_detect_resource_leak(self, agent):
        """Should detect open() without 'with' in functions."""
        code = "def read_file(path):\n    f = open(path)\n    data = f.read()\n    return data\n"
        result = agent.fallback(ValidationInput(
            target="code",
            content=code,
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "resource_leak" in codes

    def test_bare_except_ast(self, agent):
        """Should detect bare except via AST analysis."""
        code = "try:\n    x = 1\nexcept:\n    pass\n"
        result = agent.fallback(ValidationInput(
            target="code",
            content=code,
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "bare_except" in codes
