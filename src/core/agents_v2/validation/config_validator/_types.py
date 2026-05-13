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


# ──────────────────────────────────────────────────────────────
# CONFIG SCHEMAS — Known configuration schemas and their rules
# ──────────────────────────────────────────────────────────────

# Required keys per config type
REQUIRED_KEYS: dict[str, list[str]] = {
    "app": ["name", "version"],
    "database": ["host", "port", "name"],
    "server": ["host", "port"],
    "auth": ["secret_key", "algorithm"],
    "logging": ["level"],
}

# Optional keys with their default values
OPTIONAL_KEYS_WITH_DEFAULTS: dict[str, dict[str, Any]] = {
    "app": {
        "debug": False,
        "env": "production",
        "workers": 4,
    },
    "database": {
        "pool_size": 5,
        "timeout": 30,
        "ssl": True,
    },
    "server": {
        "cors_enabled": False,
        "max_request_size": 10485760,  # 10MB
        "timeout": 60,
    },
    "auth": {
        "token_expiry": 3600,
        "refresh_enabled": True,
        "max_retries": 3,
    },
    "logging": {
        "format": "json",
        "output": "stdout",
        "rotation": "1 day",
    },
}

# Value constraints: (min, max) or list of allowed values
VALUE_CONSTRAINTS: dict[str, dict[str, Any]] = {
    "app": {
        "debug": {"type": bool},
        "env": {"allowed": ["development", "staging", "production", "test"]},
        "workers": {"type": int, "min": 1, "max": 64},
        "version": {"type": str, "pattern": r"^\d+\.\d+\.\d+"},
    },
    "database": {
        "port": {"type": int, "min": 1, "max": 65535},
        "pool_size": {"type": int, "min": 1, "max": 100},
        "timeout": {"type": (int, float), "min": 1, "max": 300},
        "ssl": {"type": bool},
    },
    "server": {
        "port": {"type": int, "min": 1, "max": 65535},
        "timeout": {"type": (int, float), "min": 1, "max": 600},
        "max_request_size": {"type": int, "min": 1024, "max": 104857600},
        "cors_enabled": {"type": bool},
    },
    "auth": {
        "token_expiry": {"type": int, "min": 60, "max": 86400},
        "refresh_enabled": {"type": bool},
        "max_retries": {"type": int, "min": 0, "max": 10},
    },
    "logging": {
        "level": {"allowed": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]},
        "format": {"allowed": ["json", "text", "structured"]},
        "rotation": {"type": str},
    },
}

# Security checks: keys that should not have weak/default values
SECURITY_SENSITIVE_KEYS: dict[str, list[str]] = {
    "weak_secret_keys": [
        "change-this",
        "change-this-in-production",
        "",
        "secret",
        "password",
        "changeme",
        "default",
        "your-secret-key",
        "sk-live-key-placeholder",
    ],
    "debug_keys": ["DEBUG", "debug"],
    "dangerous_false": [],  # Keys that are dangerous when False
}


