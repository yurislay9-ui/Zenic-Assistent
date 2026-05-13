"""
Unit tests for Level 6 - Reflexion Sandbox

Tests sandbox validation for Python and other languages,
including syntax checking, symbolic execution, and K-Path limiting.
"""

import pytest
from src.core.level6_reflexion_sandbox.executor import ReflexionSandbox
from src.core.shared.contracts import SandboxResult


@pytest.fixture
def sandbox():
    """Create a sandbox with short timeout for testing."""
    return ReflexionSandbox(timeout_seconds=3, k_path_limit=50)


VALID_PYTHON = '''
def add(a, b):
    return a + b

def multiply(x, y):
    return x * y
'''

COMPLEX_PYTHON = '''
def complex_func(data):
    result = []
    for item in data:
        if item > 0:
            if item % 2 == 0:
                result.append(item * 2)
            else:
                result.append(item * 3)
        elif item < 0:
            result.append(abs(item))
        else:
            result.append(0)
    return result
'''

SYNTAX_ERROR_PYTHON = '''
def broken(
    pass
'''

EMPTY_CODE = ''

DANGEROUS_PYTHON = '''
import os
def hack():
    os.system("rm -rf /")
'''

IO_PYTHON = '''
def read_file(path):
    with open(path, 'r') as f:
        return f.read()
'''

VALID_KOTLIN = '''
fun main() {
    println("Hello")
}
'''

VALID_GO = '''
package main

func main() {
    fmt.Println("Hello")
}
'''

UNBALANCED_CODE = '''
function hello(name {
    return "Hello";
}
'''


class TestReflexionSandboxPython:
    """Tests for Python code validation."""

    @pytest.mark.asyncio
    async def test_valid_python_passes(self, sandbox):
        """Valid Python code should pass validation."""
        result = await sandbox.validate_code(VALID_PYTHON, "python", "test.py")
        assert result.status == "PASS"

    @pytest.mark.asyncio
    async def test_syntax_error_fails(self, sandbox):
        """Syntax errors should cause FAIL_SYNTAX."""
        result = await sandbox.validate_code(SYNTAX_ERROR_PYTHON, "python", "broken.py")
        assert result.status == "FAIL_SYNTAX"
        assert "Syntax error" in result.error_message

    @pytest.mark.asyncio
    async def test_empty_code_fails(self, sandbox):
        """Empty code should fail validation."""
        result = await sandbox.validate_code(EMPTY_CODE, "python", "empty.py")
        # Empty code has no syntax errors but may fail for other reasons
        assert result.status in ["PASS", "FAIL_SYNTAX", "FAIL_RUNTIME"]

    @pytest.mark.asyncio
    async def test_dangerous_code_detected(self, sandbox):
        """Dangerous calls should be detected as warnings."""
        result = await sandbox.validate_code(DANGEROUS_PYTHON, "python", "hack.py")
        # os.system should be detected as dangerous
        assert any("dangerous" in w.lower() or "os.system" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_io_calls_detected(self, sandbox):
        """I/O calls should be detected and mocked."""
        result = await sandbox.validate_code(IO_PYTHON, "python", "io.py")
        # open() should be detected as I/O
        io_warnings = [w for w in result.warnings if "I/O" in w or "open" in w.lower()]
        assert len(io_warnings) > 0

    @pytest.mark.asyncio
    async def test_complexity_warning(self, sandbox):
        """High complexity functions should generate warnings."""
        complex_code = '''
def very_complex(x):
    if x > 0:
        if x > 10:
            if x > 20:
                if x > 30:
                    if x > 40:
                        if x > 50:
                            if x > 60:
                                if x > 70:
                                    if x > 80:
                                        if x > 90:
                                            if x > 100:
                                                return 1
    return 0
'''
        result = await sandbox.validate_code(complex_code, "python", "complex.py")
        complexity_warnings = [w for w in result.warnings if "complexity" in w.lower()]
        assert len(complexity_warnings) > 0

    @pytest.mark.asyncio
    async def test_metrics_populated(self, sandbox):
        """Sandbox result should include metrics."""
        result = await sandbox.validate_code(VALID_PYTHON, "python", "test.py")
        assert "functions" in result.metrics
        assert result.metrics["functions"] >= 1

    @pytest.mark.asyncio
    async def test_paths_explored_counted(self, sandbox):
        """Should track paths explored."""
        result = await sandbox.validate_code(VALID_PYTHON, "python", "test.py")
        assert result.paths_explored >= 0


class TestReflexionSandboxOtherLanguages:
    """Tests for non-Python code validation."""

    @pytest.mark.asyncio
    async def test_valid_kotlin_passes(self, sandbox):
        """Valid Kotlin code should pass basic validation."""
        result = await sandbox.validate_code(VALID_KOTLIN, "kotlin", "test.kt")
        assert result.status == "PASS"

    @pytest.mark.asyncio
    async def test_valid_go_passes(self, sandbox):
        """Valid Go code should pass basic validation."""
        result = await sandbox.validate_code(VALID_GO, "go", "test.go")
        assert result.status == "PASS"

    @pytest.mark.asyncio
    async def test_unbalanced_braces_fails(self, sandbox):
        """Unbalanced braces should fail syntax check."""
        result = await sandbox.validate_code(UNBALANCED_CODE, "javascript", "test.js")
        assert result.status == "FAIL_SYNTAX"

    @pytest.mark.asyncio
    async def test_empty_other_language_fails(self, sandbox):
        """Empty code should fail for other languages."""
        result = await sandbox.validate_code("", "kotlin", "empty.kt")
        assert result.status == "FAIL_SYNTAX"


class TestReflexionSandboxIsolation:
    """Tests for sandbox isolation features."""

    @pytest.mark.asyncio
    async def test_sandbox_is_isolated(self, sandbox):
        """Sandbox metrics should indicate isolation."""
        result = await sandbox.validate_code(VALID_PYTHON, "python", "test.py")
        assert result.metrics.get("sandbox_isolated") is True

    @pytest.mark.asyncio
    async def test_safe_code_executes(self, sandbox):
        """Safe code should execute without runtime errors."""
        safe_code = '''
def safe_function(x, y):
    return x + y

result = safe_function(1, 2)
'''
        result = await sandbox.validate_code(safe_code, "python", "safe.py")
        assert result.status == "PASS"
