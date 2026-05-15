"""
A35 ProblemDetector — SINGLE RESPONSIBILITY: Detect the type of problem.

Deterministic keyword + pattern matching. No AI.
Detects whether a problem is api, auth, database, invoice, inventory,
crm, automation, logical, arithmetic, structural, or general.
Estimates complexity on a 0.0-1.0 scale.

Ported from:
  - ReasoningEngine._estimate_complexity() (reasoning_parts/_helpers_mixin.py)
  - ReasoningEngine._fallback_step() step 1 classification
  - ThinkingEngine._identify_template() keyword mapping
"""

from __future__ import annotations

import re
from typing import Any

from ..resilience import BaseAgent
from ..schemas import ProblemType

# ──────────────────────────────────────────────────────────────
# PROBLEM TYPE KEYWORDS — EN + ES bilingual
# ──────────────────────────────────────────────────────────────

PROBLEM_TYPE_KEYWORDS: dict[str, list[str]] = {
    "api": [
        "api", "endpoint", "rest", "route", "fastapi", "flask",
        "servidor", "server", "request", "response", "http",
        "get", "post", "put", "delete", "swagger",
    ],
    "auth": [
        "auth", "login", "seguridad", "security", "password",
        "contraseña", "token", "jwt", "oauth", "session",
        "permiso", "permission", "role", "rbac", "credential",
    ],
    "database": [
        "database", "datos", "schema", "sql", "query", "tabla",
        "table", "model", "orm", "migration", "index", "crud",
        "sqlite", "postgres", "mongo", "redis", "cache",
    ],
    "invoice": [
        "invoice", "factura", "billing", "cobro", "pago",
        "payment", "receipt", "recibo", "tax", "impuesto",
        "subtotal", "discount", "descuento",
    ],
    "inventory": [
        "inventory", "inventario", "stock", "almacen", "warehouse",
        "product", "producto", "sku", "reorder", "reabastecer",
        "movement", "movimiento", "supply", "supplier",
    ],
    "crm": [
        "crm", "cliente", "customer", "ventas", "sales",
        "pipeline", "lead", "prospecto", "deal", "oportunidad",
        "contact", "contacto", "follow-up", "seguimiento",
    ],
    "automation": [
        "automat", "workflow", "schedule", "cron", "trigger",
        "webhook", "action", "condition", "notification", "alert",
        "programado", "periódico", "event-driven", "background job",
    ],
    "logical": [
        "if", "then", "else", "condition", "logic", "boolean",
        "verify", "check", "validate", "rule", "decision",
        "si", "entonces", "sino", "condición", "regla", "decisión",
    ],
    "arithmetic": [
        "calculate", "compute", "sum", "average", "count",
        "total", "percentage", "ratio", "formula", "math",
        "calcular", "promedio", "porcentaje", "fórmula",
    ],
    "structural": [
        "refactor", "restructure", "organize", "architect",
        "design", "pattern", "module", "component", "layer",
        "refactorizar", "reestructurar", "organizar", "diseño",
        "patrón", "módulo", "componente", "capa",
    ],
}

# Priority order for problem type detection (first match wins)
TYPE_PRIORITY = [
    "auth", "invoice", "inventory", "crm", "automation",
    "api", "database", "arithmetic", "logical", "structural",
]

# ──────────────────────────────────────────────────────────────
# COMPLEXITY SIGNALS
# ──────────────────────────────────────────────────────────────

# Multi-concept connectors that increase complexity
COMPLEXITY_CONNECTORS_EN = [
    "and", "but", "however", "also", "while", "additionally",
    "moreover", "furthermore", "along with", "as well as",
]
COMPLEXITY_CONNECTORS_ES = [
    "y", "pero", "sin embargo", "además", "también",
    "mientras", "además de", "así como", "junto con",
]

# Technical terms that increase complexity
COMPLEXITY_TECH_TERMS = [
    "api", "database", "auth", "microservice", "pipeline",
    "webhook", "scheduler", "orm", "cache", "async",
    "middleware", "dependency", "integration", "streaming",
    "concurrent", "distributed", "scalable",
]


class ProblemDetector(BaseAgent[ProblemType]):
    """
    A35: Detect the type of problem from query text.

    Single Responsibility: Problem type detection ONLY.
    Method: Bilingual keyword matching + complexity estimation (deterministic).
    Fallback: Return 'general' type with medium complexity.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A35_ProblemDetector", **kwargs)

    def execute(self, input_data: Any) -> ProblemType:
        """
        Detect problem type and estimate complexity.

        input_data can be:
          - str (the query text itself)
          - dict with 'query' or 'text' key
          - Any object with .query or .text attribute
        """
        query = self._extract_query(input_data)

        if not query:
            return ProblemType(
                type="general",
                subtype="empty",
                complexity=0.0,
                source="deterministic",
            )

        # Detect problem type via keyword matching (priority order)
        detected_type = self._detect_type(query)

        # Detect subtype based on type
        subtype = self._detect_subtype(query, detected_type)

        # Estimate complexity
        complexity = self._estimate_complexity(query)

        return ProblemType(
            type=detected_type,
            subtype=subtype,
            complexity=complexity,
            source="deterministic",
        )

    def _extract_query(self, input_data: Any) -> str:
        """Extract query string from various input formats."""
        if isinstance(input_data, str):
            return input_data
        elif isinstance(input_data, dict):
            return input_data.get("query", input_data.get("text", input_data.get("description", "")))
        # Try attribute access
        for attr in ("query", "text", "description"):
            if hasattr(input_data, attr):
                return getattr(input_data, attr, "")
        return ""

    def _detect_type(self, query: str) -> str:
        """Detect the primary problem type using keyword matching."""
        query_lower = query.lower()

        for ptype in TYPE_PRIORITY:
            keywords = PROBLEM_TYPE_KEYWORDS.get(ptype, [])
            if any(kw in query_lower for kw in keywords):
                return ptype

        return "general"

    def _detect_subtype(self, query: str, ptype: str) -> str:
        """Detect the subtype within a problem type."""
        query_lower = query.lower()

        subtype_map = {
            "api": {
                "rest": ["rest", "endpoint", "route", "get", "post", "put", "delete"],
                "graphql": ["graphql", "query", "mutation"],
                "websocket": ["websocket", "ws", "socket", "real-time"],
            },
            "auth": {
                "jwt": ["jwt", "token", "bearer"],
                "oauth": ["oauth", "google auth", "github auth", "sso"],
                "basic": ["login", "password", "session", "cookie"],
            },
            "database": {
                "relational": ["sql", "postgres", "mysql", "sqlite", "tabla", "table"],
                "nosql": ["mongo", "redis", "document", "key-value"],
                "migration": ["migration", "schema change", "alter table"],
            },
            "automation": {
                "scheduled": ["schedule", "cron", "daily", "hourly", "cada", "diario"],
                "event": ["webhook", "event", "trigger", "cuando", "when"],
                "workflow": ["workflow", "pipeline", "step", "chain"],
            },
        }

        type_subtypes = subtype_map.get(ptype, {})
        for subtype, keywords in type_subtypes.items():
            if any(kw in query_lower for kw in keywords):
                return subtype

        return ""

    def _estimate_complexity(self, query: str) -> float:
        """
        Estimate problem complexity on 0.0-1.0 scale.

        Ported from ReasoningEngine._estimate_complexity().
        Signals:
          - Word count (>20: +0.2, >10: +0.1)
          - Multi-concept connectors (each: +0.1, max 0.3)
          - Technical terms (each: +0.05, max 0.2)
          - Multiple problem types detected (each additional: +0.1)
          - Deep nesting/conditions (+0.1)
        """
        score = 0.1  # Base score
        words = query.split()

        # Word count signal
        if len(words) > 20:
            score += 0.2
        elif len(words) > 10:
            score += 0.1

        # Multi-concept connectors
        query_lower = query.lower()
        connector_count = 0
        for connector in COMPLEXITY_CONNECTORS_EN + COMPLEXITY_CONNECTORS_ES:
            if connector in query_lower:
                connector_count += 1
        score += min(connector_count * 0.1, 0.3)

        # Technical terms
        tech_count = 0
        for term in COMPLEXITY_TECH_TERMS:
            if term in query_lower:
                tech_count += 1
        score += min(tech_count * 0.05, 0.2)

        # Multiple problem types detected
        types_found = 0
        for ptype, keywords in PROBLEM_TYPE_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                types_found += 1
        if types_found > 1:
            score += min((types_found - 1) * 0.1, 0.2)

        # Deep nesting / conditions
        nesting_markers = ["nested", "hierarchical", "recursive", "multiple levels",
                          "anidado", "jerárquico", "recursivo"]
        if any(m in query_lower for m in nesting_markers):
            score += 0.1

        return round(min(score, 1.0), 2)

    def detect_all_types(self, input_data: Any) -> list[tuple[str, float]]:
        """
        Detect ALL matching problem types with their match strengths.

        Returns a list of (type, strength) tuples sorted by strength descending.
        Useful for multi-domain problems.
        """
        query = self._extract_query(input_data)
        if not query:
            return []

        query_lower = query.lower()
        results: list[tuple[str, float]] = []

        for ptype, keywords in PROBLEM_TYPE_KEYWORDS.items():
            match_count = sum(1 for kw in keywords if kw in query_lower)
            if match_count > 0:
                strength = min(match_count / len(keywords) + 0.3, 1.0)
                results.append((ptype, round(strength, 2)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def fallback(self, input_data: Any) -> ProblemType:
        """Fallback: Return general type with medium complexity."""
        return ProblemType(
            type="general",
            subtype="",
            complexity=0.5,
            source="fallback",
        )
