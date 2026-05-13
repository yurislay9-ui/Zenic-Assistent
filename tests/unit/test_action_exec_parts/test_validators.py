"""
Tests for ActionResult and validator utility functions.
"""

import os
import tempfile
import pytest

from src.core.action_executor import (
    ActionResult,
    _validate_email,
    _validate_url,
    _safe_path,
    _validate_sql,
)


class TestActionResult:
    """Tests for the ActionResult dataclass."""

    def test_success_result(self):
        """ActionResult should store success state and data."""
        result = ActionResult(True, {"key": "value"})
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error == ""
        assert result.duration_ms == 0.0

    def test_failure_result_with_error(self):
        """ActionResult should store failure state and error message."""
        result = ActionResult(False, {}, "Something went wrong", 12.5)
        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.duration_ms == 12.5


class TestValidateEmail:
    """Tests for _validate_email utility."""

    def test_valid_email(self):
        assert _validate_email("user@example.com") is True

    def test_valid_email_with_dots(self):
        assert _validate_email("first.last@sub.domain.com") is True

    def test_invalid_email_no_at(self):
        assert _validate_email("userexample.com") is False

    def test_invalid_email_no_domain(self):
        assert _validate_email("user@") is False

    def test_invalid_email_empty(self):
        assert _validate_email("") is False


class TestValidateUrl:
    """Tests for _validate_url utility."""

    def test_valid_http_url(self):
        assert _validate_url("http://example.com") is True

    def test_valid_https_url(self):
        assert _validate_url("https://example.com/path") is True

    def test_invalid_url_no_scheme(self):
        assert _validate_url("example.com") is False

    def test_invalid_url_ftp(self):
        assert _validate_url("ftp://files.example.com") is False

    def test_invalid_url_empty(self):
        assert _validate_url("") is False


class TestSafePath:
    """Tests for _safe_path utility."""

    def test_safe_relative_path(self):
        """Relative path within base_dir should be allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _safe_path("file.txt", tmpdir)
            assert result.startswith(tmpdir)

    def test_path_traversal_blocked(self):
        """Path traversal with ../ should be blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="Path traversal"):
                _safe_path("../../../etc/passwd", tmpdir)

    def test_absolute_path_outside_base_blocked(self):
        """Absolute path outside base_dir should be blocked (H-05 fix)."""
        with pytest.raises(ValueError, match="Path traversal"):
            _safe_path("/tmp/test_file.txt", "/some/base")

    def test_absolute_path_within_base_allowed(self):
        """Absolute path within base_dir should be allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _safe_path(os.path.join(tmpdir, "test_file.txt"), tmpdir)
            assert result.startswith(tmpdir)


class TestValidateSql:
    """Tests for _validate_sql utility."""

    def test_safe_select_query(self):
        assert _validate_sql("SELECT * FROM users WHERE id = ?") is True

    def test_drop_table_detected(self):
        assert _validate_sql("SELECT 1; DROP TABLE users") is False

    def test_delete_from_detected(self):
        assert _validate_sql("SELECT 1; DELETE FROM users") is False

    def test_union_select_detected(self):
        assert _validate_sql("SELECT 1 UNION SELECT * FROM secrets") is False

    def test_normal_insert_passes(self):
        """Normal INSERT without dangerous patterns should pass."""
        assert _validate_sql("INSERT INTO users (name) VALUES (?)") is True
