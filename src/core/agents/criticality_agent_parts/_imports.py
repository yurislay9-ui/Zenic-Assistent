"""
Shared imports and constants for criticality_agent_parts.
"""

import re
import time
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import IntentOutput, CriticalityInput, CriticalityOutput
from src.core.agents.prompts import AgentPrompts, PromptBuilder

logger = logging.getLogger(__name__)

# ── Constantes de Criticalidad ──

# Niveles canónicos (igual que CriticalityLevel en types.py)
LEVEL_FAST = 1         # FAST_STANDARD
LEVEL_MODERATE = 2     # DEEP_MODERATE
LEVEL_SURGICAL = 3     # SURGICAL_CRITICAL

# Mapeo string → int (resuelve type mismatch)
STR_TO_LEVEL: Dict[str, int] = {
    "standard": 1, "fast": 1, "low": 1, "1": 1,
    "moderate": 2, "deep": 2, "medium": 2, "2": 2,
    "critical": 3, "surgical": 3, "high": 3, "3": 3,
    "fast_standard": 1, "deep_moderate": 2, "surgical_critical": 3,
}

# Mapeo int → DAG path (resuelve routing)
LEVEL_TO_PATH: Dict[int, str] = {
    1: "low_crit",
    2: "standard",
    3: "high_crit",
}

# Palabras clave críticas por categoría
CRITICAL_KEYWORDS = frozenset({
    "auth", "login", "password", "token", "session", "crypto",
    "encrypt", "decrypt", "hash", "ssl", "tls", "certificate",
    "payment", "credit", "debit", "bank", "transaction",
    "database", "migration", "schema", "sql", "query",
    "admin", "root", "superuser", "permission", "privilege",
    "secret", "key", "private", "credential", "api_key",
    "inject", "xss", "csrf", "vulnerability", "exploit",
    "firewall", "network", "proxy", "vpn",
})

MODERATE_KEYWORDS = frozenset({
    "api", "endpoint", "route", "controller", "service",
    "model", "repository", "factory", "builder",
    "config", "settings", "environment", "deploy",
    "middleware", "handler", "processor", "manager",
    "orchestrator", "coordinator", "scheduler",
})

# UI/Visual keywords that indicate frontend/design generation (Open Design)
UI_VISUAL_KEYWORDS = frozenset({
    "ui", "design", "interface", "frontend", "component",
    "layout", "css", "html", "react", "vue", "angular",
    "tailwind", "bootstrap", "material", "figma",
    "artifact", "render", "widget", "page", "form",
    "button", "card", "modal", "sidebar", "navbar",
    "dashboard", "panel", "dialog", "menu", "toolbar",
    "visual", "style", "theme", "animation", "responsive",
    "mobile", "tablet", "desktop", "screen", "viewport",
})

# Visual bypass criticality — forces level 1 (FAST) for UI/Design requests
VISUAL_BYPASS_REASON = "Visual bypass: UI/Design request detected — skipping Z3/AC-3 solver"

# Goals que elevan criticalidad automáticamente
GOAL_CRITICALITY_MAP: Dict[str, int] = {
    "SECURITY_HARDEN": 3,
    "BUG_FIX": 2,
    "COMPLEXITY_REDUCTION": 1,
    "MODERN_PATTERN": 1,
    "FEATURE_ADD": 2,
    "PERFORMANCE": 2,
    "READABILITY": 1,
}

# Operations que elevan criticalidad automáticamente
OP_CRITICALITY_MAP: Dict[str, int] = {
    "DELETE": 3,
    "REFACTOR": 2,
    "DEBUG": 2,
    "OPTIMIZE": 2,
    "CREATE": 2,
    "SEARCH": 1,
    "ANALYZE": 1,
    "EXPLAIN": 1,
}

# Ajustes comportamentales por nivel de criticalidad
CRITICALITY_ADJUSTMENTS: Dict[int, Dict[str, Any]] = {
    1: {  # FAST_STANDARD
        "code_agent": {
            "extra_validation": False,
            "security_checks": False,
            "error_handling": "basic",
            "docstring_level": "minimal",
            "max_complexity": 15,
        },
        "business_agent": {
            "audit_trail": False,
            "validation_layers": 1,
            "rollback": False,
            "idempotency_check": False,
        },
        "context_budget_modifier": 0.8,   # Less context needed
        "sandbox_strictness": "standard",
        "solver_required": False,
    },
    2: {  # DEEP_MODERATE
        "code_agent": {
            "extra_validation": True,
            "security_checks": False,
            "error_handling": "comprehensive",
            "docstring_level": "standard",
            "max_complexity": 10,
        },
        "business_agent": {
            "audit_trail": True,
            "validation_layers": 2,
            "rollback": True,
            "idempotency_check": False,
        },
        "context_budget_modifier": 1.0,   # Standard budget
        "sandbox_strictness": "strict",
        "solver_required": False,
    },
    3: {  # SURGICAL_CRITICAL
        "code_agent": {
            "extra_validation": True,
            "security_checks": True,
            "error_handling": "defensive",
            "docstring_level": "full",
            "max_complexity": 5,
        },
        "business_agent": {
            "audit_trail": True,
            "validation_layers": 3,
            "rollback": True,
            "idempotency_check": True,
        },
        "context_budget_modifier": 1.3,   # More context for critical ops
        "sandbox_strictness": "surgical",
        "solver_required": True,
    },
}
