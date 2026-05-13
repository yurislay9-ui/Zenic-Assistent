"""
Tests for FunctionSignature and ContextPointer data models.
"""

import pytest

from src.core.context_pointer_engine import (
    FunctionSignature, ContextPointer,
)


# ============================================================
#  FunctionSignature Tests
# ============================================================

class TestFunctionSignature:
    """Tests for FunctionSignature dataclass."""

    def test_to_pointer_format(self):
        """Should generate compact pointer representation."""
        sig = FunctionSignature(
            name="login", file_path="auth.py",
            line_start=5, line_end=10,
            params=["username:str", "password:str"],
            return_type="bool",
        )
        pointer = sig.to_pointer()
        assert "login" in pointer
        assert "username:str" in pointer
        assert "auth.py" in pointer
        assert "L5-10" in pointer

    def test_to_pointer_no_params(self):
        """Should handle empty params gracefully."""
        sig = FunctionSignature(
            name="init", file_path="main.py",
            line_start=1, line_end=1,
        )
        pointer = sig.to_pointer()
        assert "init" in pointer
        assert "()" in pointer

    def test_to_pointer_no_return_type(self):
        """Should omit return type when not specified."""
        sig = FunctionSignature(
            name="process", file_path="app.py",
            line_start=10, line_end=15,
            params=["data"],
        )
        pointer = sig.to_pointer()
        assert "->" not in pointer


# ============================================================
#  ContextPointer Tests
# ============================================================

class TestContextPointer:
    """Tests for ContextPointer dataclass and methods."""

    def test_to_model_context_with_docstring(self):
        """Should include docstring in model context."""
        sig = FunctionSignature(
            name="login", file_path="auth.py",
            line_start=5, line_end=10,
            docstring="Authenticate user",
        )
        ptr = ContextPointer(signature=sig, reason="User asked about login")
        ctx = ptr.to_model_context()
        assert "login" in ctx
        assert "Authenticate user" in ctx
        assert "User asked about login" in ctx

    def test_to_model_context_with_calls(self):
        """Should include call list in model context."""
        sig = FunctionSignature(
            name="login", file_path="auth.py",
            line_start=5, line_end=10,
            calls=["verify_password", "create_token"],
        )
        ptr = ContextPointer(signature=sig)
        ctx = ptr.to_model_context()
        assert "verify_password" in ctx

    def test_to_model_context_minimal(self):
        """Should work with minimal signature info."""
        sig = FunctionSignature(
            name="noop", file_path="utils.py",
            line_start=1, line_end=1,
        )
        ptr = ContextPointer(signature=sig)
        ctx = ptr.to_model_context()
        assert "noop" in ctx

    def test_load_code_from_disk(self, tmp_path):
        """Should load code lines from file using line range."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\nline4\nline5\n")
        sig = FunctionSignature(
            name="test_func", file_path=str(test_file),
            line_start=2, line_end=4,
        )
        ptr = ContextPointer(signature=sig)
        code = ptr.load_code_from_disk()
        assert "line2" in code
        assert "line3" in code
        assert "line4" in code
        assert "line1" not in code

    def test_load_code_nonexistent_file(self):
        """Should return empty string for nonexistent file."""
        sig = FunctionSignature(
            name="missing", file_path="/nonexistent/file.py",
            line_start=1, line_end=5,
        )
        ptr = ContextPointer(signature=sig)
        code = ptr.load_code_from_disk()
        assert code == ""

    def test_apply_modification(self, tmp_path):
        """Should replace lines in the target file."""
        test_file = tmp_path / "mod.py"
        test_file.write_text("def old():\n    pass\n\ndef other():\n    pass\n")
        sig = FunctionSignature(
            name="old", file_path=str(test_file),
            line_start=1, line_end=2,
        )
        ptr = ContextPointer(signature=sig)
        result = ptr.apply_modification("def new():\n    return 42")
        assert result is True
        content = test_file.read_text()
        assert "def new():" in content
        assert "return 42" in content

    def test_apply_modification_nonexistent_file(self):
        """Should return False for nonexistent file."""
        sig = FunctionSignature(
            name="old", file_path="/nonexistent/file.py",
            line_start=1, line_end=2,
        )
        ptr = ContextPointer(signature=sig)
        result = ptr.apply_modification("def new(): pass")
        assert result is False

    def test_apply_modification_with_sibling_adjustment(self, tmp_path):
        """Should adjust sibling pointer line numbers after modification."""
        test_file = tmp_path / "siblings.py"
        test_file.write_text(
            "def func_a():\n    pass\n\ndef func_b():\n    pass\n\ndef func_c():\n    pass\n"
        )
        sig_a = FunctionSignature(name="func_a", file_path=str(test_file), line_start=1, line_end=2)
        sig_b = FunctionSignature(name="func_b", file_path=str(test_file), line_start=4, line_end=5)
        sig_c = FunctionSignature(name="func_c", file_path=str(test_file), line_start=7, line_end=8)

        ptr_a = ContextPointer(signature=sig_a)
        ptr_b = ContextPointer(signature=sig_b)
        ptr_c = ContextPointer(signature=sig_c)

        # Expand func_a by 2 extra lines
        ptr_a.apply_modification(
            "def func_a():\n    extra_line_1\n    extra_line_2\n    pass",
            sibling_pointers=[ptr_b, ptr_c],
        )

        # func_b and func_c should be shifted by +2
        assert sig_b.line_start == 6
        assert sig_b.line_end == 7
        assert sig_c.line_start == 9
        assert sig_c.line_end == 10
