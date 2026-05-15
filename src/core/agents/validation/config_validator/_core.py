"""
A26 ConfigValidator — SINGLE RESPONSIBILITY: Validate configuration schemas and values.

Deterministic. No AI.
Validates:
  1. Config format (JSON/YAML/dict parsing)
  2. Required keys presence
  3. Type correctness of values
  4. Security best practices (DEBUG mode, SECRET_KEY, etc.)
  5. Value range/bound checks
  6. Default value application for missing optional keys
"""

from __future__ import annotations
import json
from typing import Any, Optional
from ...resilience import BaseAgent
from ...schemas import ConfigResult, ValidationIssue
from ._types import REQUIRED_KEYS, OPTIONAL_KEYS_WITH_DEFAULTS, VALUE_CONSTRAINTS, SECURITY_SENSITIVE_KEYS

class ConfigValidator(BaseAgent[ConfigResult]):
    """
    A26: Validate configuration schemas and values.

    Single Responsibility: Configuration validation ONLY.
    Method: Schema checks + type validation + security best practices (deterministic).
    Fallback: Return valid=True with defaults applied (trust when cannot parse).
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A26_ConfigValidator", **kwargs)

    def execute(self, input_data: Any) -> ConfigResult:
        """
        Validate configuration data.

        input_data should be a dict with:
          - 'config': The config to validate (dict, JSON string, or YAML string)
          - 'config_type': Optional str — type of config ("app", "database", etc.)
          - 'schema': Optional dict — custom schema to validate against
        """
        if not isinstance(input_data, dict):
            return self.fallback(input_data)

        config_data = input_data.get("config", input_data)
        config_type = input_data.get("config_type", "")
        custom_schema = input_data.get("schema", None)

        # Parse config data
        config, parse_issues = self._parse_config(config_data)
        if not config:
            return ConfigResult(
                valid=False,
                issues=parse_issues,
                defaults_applied=[],
                source="deterministic",
            )

        issues = list(parse_issues)
        defaults_applied: list[str] = []

        # 1. Schema validation (required keys)
        if config_type and config_type in REQUIRED_KEYS:
            schema_issues, applied = self._validate_required_keys(
                config, config_type
            )
            issues.extend(schema_issues)
            defaults_applied.extend(applied)

        # 2. Type and constraint validation
        if config_type and config_type in VALUE_CONSTRAINTS:
            constraint_issues = self._validate_constraints(config, config_type)
            issues.extend(constraint_issues)

        # 3. Custom schema validation
        if custom_schema:
            custom_issues, applied = self._validate_custom_schema(
                config, custom_schema
            )
            issues.extend(custom_issues)
            defaults_applied.extend(applied)

        # 4. Security best practices
        security_issues = self._validate_security(config)
        issues.extend(security_issues)

        # 5. Apply defaults for missing optional keys
        if config_type and config_type in OPTIONAL_KEYS_WITH_DEFAULTS:
            applied = self._apply_defaults(config, config_type)
            defaults_applied.extend(applied)

        # Determine validity
        has_errors = any(i.severity == "error" for i in issues)
        valid = not has_errors

        return ConfigResult(
            valid=valid,
            issues=issues,
            defaults_applied=defaults_applied,
            source="deterministic",
        )

    def _parse_config(
        self, config_data: Any
    ) -> tuple[Optional[dict[str, Any]], list[ValidationIssue]]:
        """Parse config data from various formats into a dict."""
        issues = []

        if isinstance(config_data, dict):
            return config_data, issues

        if isinstance(config_data, str):
            # Try JSON first
            try:
                parsed = json.loads(config_data)
                if isinstance(parsed, dict):
                    return parsed, issues
            except (json.JSONDecodeError, TypeError):
                pass

            # Try YAML
            try:
                import yaml

                parsed = yaml.safe_load(config_data)
                if isinstance(parsed, dict):
                    return parsed, issues
            except ImportError:
                pass
            except Exception:
                pass

            issues.append(
                ValidationIssue(
                    severity="error",
                    code="invalid_format",
                    message="Config is not valid JSON or YAML",
                    suggestion="Check syntax and format",
                )
            )
            return None, issues

        # Try to convert object to dict
        if hasattr(config_data, "__dict__"):
            return vars(config_data), issues

        issues.append(
            ValidationIssue(
                severity="error",
                code="unsupported_type",
                message=f"Config type '{type(config_data).__name__}' is not supported",
                suggestion="Provide config as dict, JSON string, or YAML string",
            )
        )
        return None, issues

    def _validate_required_keys(
        self, config: dict[str, Any], config_type: str
    ) -> tuple[list[ValidationIssue], list[str]]:
        """Validate that all required keys are present."""
        issues = []
        defaults_applied = []

        required = REQUIRED_KEYS.get(config_type, [])
        for key in required:
            if key not in config:
                # Check if there's a default
                defaults = OPTIONAL_KEYS_WITH_DEFAULTS.get(config_type, {})
                if key in defaults:
                    config[key] = defaults[key]
                    defaults_applied.append(key)
                else:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            code="missing_required_key",
                            message=f"Required key '{key}' is missing from {config_type} config",
                            suggestion=f"Add the '{key}' key to your configuration",
                        )
                    )

        return issues, defaults_applied

    def _validate_constraints(
        self, config: dict[str, Any], config_type: str
    ) -> list[ValidationIssue]:
        """Validate value types and constraints."""
        issues = []
        constraints = VALUE_CONSTRAINTS.get(config_type, {})

        for key, rules in constraints.items():
            if key not in config:
                continue  # Missing keys handled in required_keys validation

            value = config[key]

            # Type check
            expected_type = rules.get("type")
            if expected_type and not isinstance(value, expected_type):
                type_name = (
                    expected_type.__name__
                    if isinstance(expected_type, type)
                    else str(expected_type)
                )
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="type_mismatch",
                        message=f"Key '{key}' expected type {type_name}, got {type(value).__name__}",
                        suggestion=f"Change '{key}' to type {type_name}",
                    )
                )
                continue

            # Allowed values
            allowed = rules.get("allowed")
            if allowed and value not in allowed:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="invalid_value",
                        message=f"Key '{key}' value '{value}' not in allowed values: {allowed}",
                        suggestion=f"Use one of: {', '.join(str(a) for a in allowed)}",
                    )
                )

            # Min/Max bounds
            min_val = rules.get("min")
            max_val = rules.get("max")
            if isinstance(value, (int, float)):
                if min_val is not None and value < min_val:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            code="value_too_low",
                            message=f"Key '{key}' value {value} is below minimum {min_val}",
                            suggestion=f"Increase '{key}' to at least {min_val}",
                        )
                    )
                if max_val is not None and value > max_val:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            code="value_too_high",
                            message=f"Key '{key}' value {value} exceeds maximum {max_val}",
                            suggestion=f"Reduce '{key}' to at most {max_val}",
                        )
                    )

            # Pattern match
            import re

            pattern = rules.get("pattern")
            if pattern and isinstance(value, str):
                if not re.match(pattern, value):
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="pattern_mismatch",
                            message=f"Key '{key}' value '{value}' does not match expected pattern",
                            suggestion=f"Update '{key}' to match the expected format",
                        )
                    )

        return issues

    def _validate_custom_schema(
        self, config: dict[str, Any], schema: dict[str, Any]
    ) -> tuple[list[ValidationIssue], list[str]]:
        """Validate against a custom user-provided schema."""
        issues = []
        defaults_applied = []

        required = schema.get("required", [])
        for key in required:
            if key not in config:
                default_val = schema.get("defaults", {}).get(key)
                if default_val is not None:
                    config[key] = default_val
                    defaults_applied.append(key)
                else:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            code="missing_required_key",
                            message=f"Custom schema requires key '{key}'",
                            suggestion=f"Add the '{key}' key to your configuration",
                        )
                    )

        return issues, defaults_applied

    def _validate_security(self, config: dict[str, Any]) -> list[ValidationIssue]:
        """Check for security best practices."""
        issues = []

        # Check for DEBUG mode enabled
        for key in SECURITY_SENSITIVE_KEYS["debug_keys"]:
            if key in config:
                if config[key] is True or (
                    isinstance(config[key], str)
                    and config[key].lower() in ("true", "1", "yes")
                ):
                    issues.append(
                        ValidationIssue(
                            severity="info",
                            code="debug_enabled",
                            message="DEBUG mode is enabled — disable in production",
                            suggestion="Set DEBUG=false for production environments",
                        )
                    )

        # Check for weak SECRET_KEY
        secret_key = config.get("SECRET_KEY") or config.get("secret_key")
        if secret_key:
            weak_keys = SECURITY_SENSITIVE_KEYS["weak_secret_keys"]
            if str(secret_key) in weak_keys:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="weak_secret_key",
                        message="Default or weak SECRET_KEY detected — security risk",
                        suggestion="Generate a strong secret key for production",
                    )
                )
            elif isinstance(secret_key, str) and len(secret_key) < 16:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="short_secret_key",
                        message=f"SECRET_KEY is only {len(secret_key)} characters — recommend at least 32",
                        suggestion="Use a secret key with at least 32 characters",
                    )
                )

        # Check for database SSL disabled
        db_ssl = config.get("ssl")
        if db_ssl is False:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="ssl_disabled",
                    message="Database SSL is disabled — data may be transmitted unencrypted",
                    suggestion="Enable SSL for database connections in production",
                )
            )

        # Check for insecure CORS
        cors_origins = config.get("cors_origins") or config.get("CORS_ORIGINS")
        if cors_origins == "*" or cors_origins == ["*"]:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="cors_wildcard",
                    message="CORS allows all origins (*) — restrict to specific domains",
                    suggestion="Set CORS_ORIGINS to specific allowed domains",
                )
            )

        # Check for missing TLS in server config
        host = config.get("host", "")
        port = config.get("port", 0)
        if isinstance(host, str) and host == "0.0.0.0":
            issues.append(
                ValidationIssue(
                    severity="info",
                    code="bind_all_interfaces",
                    message="Server binding to all interfaces (0.0.0.0) — verify this is intended",
                    suggestion="Bind to specific interface if not serving publicly",
                )
            )

        return issues

    def _apply_defaults(
        self, config: dict[str, Any], config_type: str
    ) -> list[str]:
        """Apply default values for missing optional keys."""
        applied = []
        defaults = OPTIONAL_KEYS_WITH_DEFAULTS.get(config_type, {})

        for key, default_value in defaults.items():
            if key not in config:
                config[key] = default_value
                applied.append(key)

        return applied

    def fallback(self, input_data: Any) -> ConfigResult:
        """
        Fallback: Return valid=True with no defaults.
        When config cannot be parsed, we trust by default.
        The VerdictEngine will still catch issues at the consensus level.
        """
        return ConfigResult(valid=True, source="fallback")
