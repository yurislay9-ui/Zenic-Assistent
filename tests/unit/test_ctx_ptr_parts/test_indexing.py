"""
Tests for Python and regex-based signature indexing.
"""

import pytest

from src.core.context_pointer_engine import (
    FunctionSignature, ContextPointer, SignatureIndex, CONTEXT_STORE_ROOT,
)

from .conftest import SAMPLE_PYTHON_CODE, SAMPLE_JS_CODE


# ============================================================
#  SignatureIndex - Python Indexing Tests
# ============================================================

class TestPythonIndexing:
    """Tests for Python code signature extraction."""

    def test_index_python_code(self, signature_index):
        """Should extract function signatures from Python code."""
        count = signature_index.index_code(SAMPLE_PYTHON_CODE, "auth.py")
        assert count >= 3  # login, logout, UserAuth (and possibly authenticate)

    def test_index_function_names(self, populated_index):
        """Should correctly index function names."""
        names = [key[0] if isinstance(key, tuple) else key for key in populated_index._name_index.keys()]
        assert "login" in names
        assert "logout" in names

    def test_index_class_signatures(self, populated_index):
        """Should index class definitions with method info."""
        names = [key[0] if isinstance(key, tuple) else key for key in populated_index._name_index.keys()]
        assert "UserAuth" in names

    def test_index_function_params(self, populated_index):
        """Should extract parameter names and types."""
        login_sigs = populated_index._name_index.get(("login", "auth.py"), [])
        assert len(login_sigs) >= 1
        params = login_sigs[0].params
        assert any("username" in p for p in params)
        assert any("password" in p for p in params)

    def test_index_function_return_type(self, populated_index):
        """Should extract return type annotations."""
        login_sigs = populated_index._name_index.get(("login", "auth.py"), [])
        assert len(login_sigs) >= 1
        assert login_sigs[0].return_type == "bool"

    def test_index_function_docstring(self, populated_index):
        """Should extract docstrings."""
        login_sigs = populated_index._name_index.get(("login", "auth.py"), [])
        assert len(login_sigs) >= 1
        assert "Authenticate" in login_sigs[0].docstring

    def test_index_function_calls(self, populated_index):
        """Should extract function call references."""
        login_sigs = populated_index._name_index.get(("login", "auth.py"), [])
        assert len(login_sigs) >= 1
        # login calls create_token and verify_password
        assert "create_token" in login_sigs[0].calls or "verify_password" in login_sigs[0].calls

    def test_index_function_complexity(self, populated_index):
        """Should compute cyclomatic complexity."""
        login_sigs = populated_index._name_index.get(("login", "auth.py"), [])
        assert len(login_sigs) >= 1
        # login has an if statement → complexity >= 2
        assert login_sigs[0].complexity >= 2

    def test_index_function_hash(self, populated_index):
        """Should compute content hash."""
        login_sigs = populated_index._name_index.get(("login", "auth.py"), [])
        assert len(login_sigs) >= 1
        assert login_sigs[0].hash != ""


# ============================================================
#  SignatureIndex - Regex Indexing Tests
# ============================================================

class TestRegexIndexing:
    """Tests for non-Python code signature extraction via regex."""

    def test_index_javascript_code(self, signature_index):
        """Should extract JS function signatures."""
        count = signature_index.index_code(SAMPLE_JS_CODE, "app.js")
        assert count >= 1
        names = [key[0] if isinstance(key, tuple) else key for key in signature_index._name_index.keys()]
        assert "handleClick" in names or "fetchData" in names

    def test_index_unknown_language(self, signature_index):
        """Should fallback to generic regex for unknown extensions."""
        code = "def some_func(arg1, arg2)"
        count = signature_index.index_code(code, "unknown.xyz")
        # May or may not match; just should not crash
        assert isinstance(count, int)

    def test_index_kotlin_code(self, signature_index):
        """Should extract Kotlin function signatures."""
        kt_code = "fun calculateTotal(price: Double, qty: Int): Double { return price * qty }"
        count = signature_index.index_code(kt_code, "calc.kt")
        assert count >= 1
        names = [key[0] if isinstance(key, tuple) else key for key in signature_index._name_index.keys()]
        assert "calculateTotal" in names
