"""
ZENIC-AGENTS - EnvLoader Tests

Tests for the pure-Python .env loader:
  - _parse_env_line: KEY=VALUE parsing, quotes, comments
  - load_env: loading from .env, skip existing vars, force reload
  - get_env, get_env_int, get_env_bool, get_env_list
  - get_github_token, get_metrics_config, get_scraper_config
  - Thread-safe single-load guarantee
"""

import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock

import src.core.env_loader as env_loader


# ============================================================
#  FIXTURES
# ============================================================

@pytest.fixture(autouse=True)
def reset_loader_state():
    """Reset the module-level state before each test."""
    env_loader._loaded = False
    env_loader._loaded_path = None
    yield
    env_loader._loaded = False
    env_loader._loaded_path = None


@pytest.fixture
def env_file(tmp_path):
    """Create a temporary .env file."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        'GITHUB_TOKEN=ghp_test123\n'
        'DATABASE_URL="postgres://localhost/mydb"\n'
        "SECRET_KEY='my_secret_key'\n"
        "EMPTY_VAR=\n"
        "# This is a comment\n"
        "\n"
        "NO_EQUALS_LINE\n"
        "=NO_KEY\n"
        "PORT=8080\n"
        "FEATURE_ENABLED=true\n"
        "TAGS=python,fastapi,api\n"
    )
    return env_path


# ============================================================
#  PARSE ENV LINE TESTS
# ============================================================

class TestParseEnvLine:
    """Tests for _parse_env_line."""

    def test_simple_key_value(self):
        result = env_loader._parse_env_line("KEY=value")
        assert result == ("KEY", "value")

    def test_key_with_equals_in_value(self):
        result = env_loader._parse_env_line("KEY=value=with=equals")
        assert result is not None
        key, value = result
        assert key == "KEY"
        assert value == "value=with=equals"

    def test_double_quoted_value(self):
        result = env_loader._parse_env_line('KEY="value with spaces"')
        assert result == ("KEY", "value with spaces")

    def test_single_quoted_value(self):
        result = env_loader._parse_env_line("KEY='value with spaces'")
        assert result == ("KEY", "value with spaces")

    def test_empty_value(self):
        result = env_loader._parse_env_line("KEY=")
        assert result == ("KEY", "")

    def test_comment_line(self):
        result = env_loader._parse_env_line("# This is a comment")
        assert result is None

    def test_empty_line(self):
        result = env_loader._parse_env_line("")
        assert result is None

    def test_whitespace_only_line(self):
        result = env_loader._parse_env_line("   ")
        assert result is None

    def test_no_equals_sign(self):
        result = env_loader._parse_env_line("NO_EQUALS")
        assert result is None

    def test_no_key(self):
        result = env_loader._parse_env_line("=value_without_key")
        assert result is None

    def test_whitespace_around_key_value(self):
        result = env_loader._parse_env_line("  KEY  =  value  ")
        assert result == ("KEY", "value")

    def test_single_char_value(self):
        """Single character should not be treated as quoted."""
        result = env_loader._parse_env_line('KEY="')
        assert result is not None
        # Not a matching pair of quotes, so value stays as-is


# ============================================================
#  LOAD ENV TESTS
# ============================================================

class TestLoadEnv:
    """Tests for load_env."""

    def test_load_from_env_file(self, env_file):
        """load_env should parse .env and set variables."""
        with patch.object(env_loader, "_find_env_file", return_value=env_file):
            # Remove vars if they exist
            os.environ.pop("GITHUB_TOKEN", None)
            os.environ.pop("PORT", None)

            result = env_loader.load_env()
            assert result is True
            assert os.environ.get("GITHUB_TOKEN") == "ghp_test123"
            assert os.environ.get("PORT") == "8080"

            # Cleanup
            os.environ.pop("GITHUB_TOKEN", None)
            os.environ.pop("PORT", None)

    def test_skip_existing_env_vars(self, env_file):
        """Variables already in os.environ should NOT be overwritten."""
        os.environ["GITHUB_TOKEN"] = "existing_value"
        try:
            with patch.object(env_loader, "_find_env_file", return_value=env_file):
                env_loader.load_env()
                assert os.environ["GITHUB_TOKEN"] == "existing_value"
        finally:
            os.environ.pop("GITHUB_TOKEN", None)

    def test_no_env_file_returns_false(self):
        """When no .env file found, load_env should return False."""
        with patch.object(env_loader, "_find_env_file", return_value=None):
            result = env_loader.load_env()
            assert result is False

    def test_load_only_once(self, env_file):
        """Without force=True, load_env should only load once."""
        with patch.object(env_loader, "_find_env_file", return_value=env_file) as mock_find:
            os.environ.pop("PORT", None)
            env_loader.load_env()
            env_loader.load_env()  # Second call
            # _find_env_file should only be called once
            assert mock_find.call_count == 1
            os.environ.pop("PORT", None)

    def test_force_reload(self, env_file):
        """With force=True, load_env should reload even if already loaded."""
        with patch.object(env_loader, "_find_env_file", return_value=env_file) as mock_find:
            os.environ.pop("PORT", None)
            env_loader.load_env()
            env_loader.load_env(force=True)
            assert mock_find.call_count == 2
            os.environ.pop("PORT", None)

    def test_double_quoted_values_stripped(self, env_file):
        """Double-quoted values should have quotes stripped."""
        with patch.object(env_loader, "_find_env_file", return_value=env_file):
            os.environ.pop("DATABASE_URL", None)
            env_loader.load_env()
            assert os.environ.get("DATABASE_URL") == "postgres://localhost/mydb"
            os.environ.pop("DATABASE_URL", None)

    def test_single_quoted_values_stripped(self, env_file):
        """Single-quoted values should have quotes stripped."""
        with patch.object(env_loader, "_find_env_file", return_value=env_file):
            os.environ.pop("SECRET_KEY", None)
            env_loader.load_env()
            assert os.environ.get("SECRET_KEY") == "my_secret_key"
            os.environ.pop("SECRET_KEY", None)


# ============================================================
#  GET ENV HELPER TESTS
# ============================================================

class TestGetEnvHelpers:
    """Tests for get_env, get_env_int, get_env_bool, get_env_list."""

    def test_get_env_existing(self):
        """get_env should return value for existing key."""
        os.environ["TEST_VAR_X"] = "hello"
        try:
            result = env_loader.get_env("TEST_VAR_X")
            assert result == "hello"
        finally:
            os.environ.pop("TEST_VAR_X", None)

    def test_get_env_missing_with_default(self):
        """get_env should return default for missing key."""
        os.environ.pop("NONEXISTENT_VAR_XYZ", None)
        result = env_loader.get_env("NONEXISTENT_VAR_XYZ", default="fallback")
        assert result == "fallback"

    def test_get_env_int(self):
        """get_env_int should parse integer values."""
        os.environ["TEST_INT_X"] = "42"
        try:
            result = env_loader.get_env_int("TEST_INT_X")
            assert result == 42
        finally:
            os.environ.pop("TEST_INT_X", None)

    def test_get_env_int_invalid(self):
        """get_env_int should return default for non-integer values."""
        os.environ["TEST_INT_INVALID_X"] = "not_a_number"
        try:
            result = env_loader.get_env_int("TEST_INT_INVALID_X", default=99)
            assert result == 99
        finally:
            os.environ.pop("TEST_INT_INVALID_X", None)

    def test_get_env_bool_true_values(self):
        """get_env_bool should return True for truthy strings."""
        for val in ("true", "yes", "1", "on"):
            os.environ["TEST_BOOL_X"] = val
            assert env_loader.get_env_bool("TEST_BOOL_X") is True
        os.environ.pop("TEST_BOOL_X", None)

    def test_get_env_bool_false_values(self):
        """get_env_bool should return False for falsy strings."""
        for val in ("false", "no", "0", "off"):
            os.environ["TEST_BOOL_X"] = val
            assert env_loader.get_env_bool("TEST_BOOL_X") is False
        os.environ.pop("TEST_BOOL_X", None)

    def test_get_env_bool_empty_uses_default(self):
        """get_env_bool should return default for empty/missing values."""
        os.environ.pop("TEST_BOOL_MISSING_X", None)
        result = env_loader.get_env_bool("TEST_BOOL_MISSING_X", default=True)
        assert result is True

    def test_get_env_list(self):
        """get_env_list should split comma-separated values."""
        os.environ["TEST_LIST_X"] = "python,fastapi,api"
        try:
            result = env_loader.get_env_list("TEST_LIST_X")
            assert result == ["python", "fastapi", "api"]
        finally:
            os.environ.pop("TEST_LIST_X", None)

    def test_get_env_list_empty(self):
        """get_env_list should return empty list for missing key."""
        os.environ.pop("TEST_LIST_MISSING_X", None)
        result = env_loader.get_env_list("TEST_LIST_MISSING_X")
        assert result == []

    def test_get_env_list_custom_separator(self):
        """get_env_list should support custom separators."""
        os.environ["TEST_LIST_SEP_X"] = "a;b;c"
        try:
            result = env_loader.get_env_list("TEST_LIST_SEP_X", separator=";")
            assert result == ["a", "b", "c"]
        finally:
            os.environ.pop("TEST_LIST_SEP_X", None)


# ============================================================
#  CONFIG HELPER TESTS
# ============================================================

class TestConfigHelpers:
    """Tests for get_github_token, get_metrics_config, get_scraper_config."""

    def test_get_github_token_primary(self):
        """get_github_token should check GITHUB_TOKEN first."""
        os.environ["GITHUB_TOKEN"] = "ghp_primary"
        os.environ.pop("GITHUB_API_KEY", None)
        try:
            assert env_loader.get_github_token() == "ghp_primary"
        finally:
            os.environ.pop("GITHUB_TOKEN", None)

    def test_get_github_token_fallback(self):
        """get_github_token should fallback to GITHUB_API_KEY."""
        os.environ.pop("GITHUB_TOKEN", None)
        os.environ["GITHUB_API_KEY"] = "ghp_fallback"
        try:
            assert env_loader.get_github_token() == "ghp_fallback"
        finally:
            os.environ.pop("GITHUB_API_KEY", None)

    def test_get_metrics_config(self):
        """get_metrics_config should return a dict with expected keys."""
        config = env_loader.get_metrics_config()
        assert "enabled" in config
        assert "collect" in config
        assert "refresh_interval" in config

    def test_get_scraper_config(self):
        """get_scraper_config should return a dict with expected keys."""
        config = env_loader.get_scraper_config()
        assert "timeout" in config
        assert "max_retries" in config
        assert "github_token" in config
        assert "preferred_source" in config

    def test_get_loaded_path_none_initially(self):
        """get_loaded_path should return None before loading."""
        assert env_loader.get_loaded_path() is None

    def test_get_loaded_path_after_load(self, env_file):
        """get_loaded_path should return the path after loading."""
        with patch.object(env_loader, "_find_env_file", return_value=env_file):
            env_loader.load_env()
            assert env_loader.get_loaded_path() is not None
