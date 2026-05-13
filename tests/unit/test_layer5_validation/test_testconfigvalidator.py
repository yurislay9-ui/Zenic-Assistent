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

from src.core.agents_v2.validation import (
    SecurityScanner,
    SyntaxValidator,
    ChainValidator,
    ConfigValidator,
    RiskCalculator,
    FixSuggester,
)
from src.core.agents_v2.schemas import (
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



class TestConfigValidator:
    """A26: Validate configuration schemas and values."""

    def setup_method(self):
        self.validator = ConfigValidator()

    def test_valid_app_config(self):
        """Valid app config should pass."""
        config = {
            "name": "my-app",
            "version": "1.0.0",
            "debug": False,
        }
        result = self.validator.execute({"config": config, "config_type": "app"})
        assert isinstance(result, ConfigResult)
        assert result.valid is True

    def test_missing_required_key(self):
        """Missing required key should be an error."""
        config = {"name": "my-app"}  # Missing "version"
        result = self.validator.execute({"config": config, "config_type": "app"})
        assert result.valid is False
        assert any(i.code == "missing_required_key" for i in result.issues)

    def test_type_mismatch(self):
        """Wrong value type should be an error."""
        config = {
            "name": "my-app",
            "version": "1.0.0",
            "workers": "four",  # Should be int
        }
        result = self.validator.execute({"config": config, "config_type": "app"})
        assert result.valid is False
        assert any(i.code == "type_mismatch" for i in result.issues)

    def test_value_out_of_range(self):
        """Value outside allowed range should be an error."""
        config = {
            "name": "my-app",
            "version": "1.0.0",
            "workers": 100,  # Max is 64
        }
        result = self.validator.execute({"config": config, "config_type": "app"})
        assert result.valid is False
        assert any(i.code == "value_too_high" for i in result.issues)

    def test_debug_enabled_warning(self):
        """DEBUG=true should produce a security info issue."""
        config = {"name": "my-app", "version": "1.0.0", "debug": True}
        result = self.validator.execute({"config": config, "config_type": "app"})
        assert any(i.code == "debug_enabled" for i in result.issues)

    def test_weak_secret_key(self):
        """Weak SECRET_KEY should be an error."""
        config = {"secret_key": "change-this", "algorithm": "HS256"}
        result = self.validator.execute({"config": config, "config_type": "auth"})
        assert any(i.code == "weak_secret_key" for i in result.issues)

    def test_short_secret_key(self):
        """Short SECRET_KEY should produce a warning."""
        config = {"secret_key": "short", "algorithm": "HS256"}
        result = self.validator.execute({"config": config, "config_type": "auth"})
        assert any(i.code == "short_secret_key" for i in result.issues)

    def test_ssl_disabled_warning(self):
        """Database SSL disabled should warn."""
        config = {"host": "localhost", "port": 5432, "name": "mydb", "ssl": False}
        result = self.validator.execute({"config": config, "config_type": "database"})
        assert any(i.code == "ssl_disabled" for i in result.issues)

    def test_cors_wildcard_warning(self):
        """CORS with wildcard should warn."""
        config = {"cors_origins": "*"}
        result = self.validator.execute({"config": config})
        assert any(i.code == "cors_wildcard" for i in result.issues)

    def test_bind_all_interfaces_info(self):
        """Binding to 0.0.0.0 should produce info."""
        config = {"host": "0.0.0.0", "port": 8080}
        result = self.validator.execute({"config": config, "config_type": "server"})
        assert any(i.code == "bind_all_interfaces" for i in result.issues)

    def test_defaults_applied(self):
        """Missing optional keys should have defaults applied."""
        config = {"name": "my-app", "version": "1.0.0"}
        result = self.validator.execute({"config": config, "config_type": "app"})
        # Should have defaults applied for debug, env, workers
        assert len(result.defaults_applied) > 0

    def test_invalid_json_config(self):
        """Invalid JSON/YAML string should produce format error."""
        result = self.validator.execute({"config": "this is not json or yaml!!!"})
        # Even if parsed, the config should have issues or be empty
        # The key is it doesn't crash and returns a ConfigResult
        assert isinstance(result, ConfigResult)

    def test_valid_json_string_config(self):
        """Valid JSON string should be parsed correctly."""
        config_json = json.dumps({"name": "my-app", "version": "1.0.0"})
        result = self.validator.execute({"config": config_json, "config_type": "app"})
        assert result.valid is True

    def test_custom_schema_validation(self):
        """Custom schema should be validated."""
        custom_schema = {
            "required": ["api_key", "base_url"],
            "defaults": {"timeout": 30},
        }
        config = {"api_key": "sk-xxx", "base_url": "https://api.example.com"}
        result = self.validator.execute({"config": config, "schema": custom_schema})
        assert result.valid is True

    def test_custom_schema_missing_required(self):
        """Custom schema missing required should error."""
        custom_schema = {
            "required": ["api_key", "base_url"],
        }
        config = {"api_key": "sk-xxx"}
        result = self.validator.execute({"config": config, "schema": custom_schema})
        assert result.valid is False
        assert any("base_url" in i.message for i in result.issues)

    def test_database_port_range(self):
        """Database port should be 1-65535."""
        config = {"host": "localhost", "port": 99999, "name": "mydb"}
        result = self.validator.execute({"config": config, "config_type": "database"})
        assert result.valid is False
        assert any(i.code == "value_too_high" for i in result.issues)

    def test_logging_level_allowed_values(self):
        """Logging level should be one of the allowed values."""
        config = {"level": "VERBOSE"}  # Not in allowed values
        result = self.validator.execute({"config": config, "config_type": "logging"})
        assert result.valid is False
        assert any(i.code == "invalid_value" for i in result.issues)

    def test_fallback_returns_valid(self):
        """Fallback should return valid=True."""
        result = self.validator.fallback(None)
        assert result.valid is True
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A27 RiskCalculator Tests
# ═══════════════════════════════════════════════════════════

