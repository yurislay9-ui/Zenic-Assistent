"""
A37 TemplateReasoner — SINGLE RESPONSIBILITY: Apply template-based reasoning for known problem types.

Deterministic template matching. No AI.
Uses lookup tables for known problem types and produces
structured answers with confidence scores.

Ported from:
  - ReasoningEngine._fallback_generate() (reasoning_parts/_helpers_mixin.py)
  - ReasoningEngine._fallback_step() step 1-3 (reasoning_parts/_helpers_mixin.py)
  - ReasoningEngine._fallback_context_reasoning() (reasoning_parts/_helpers_mixin.py)
  - ThinkingEngine._identify_template() keyword mapping
"""

from __future__ import annotations

import re
from typing import Any, Optional

from ..resilience import BaseAgent
from ..schemas import ProblemType, ReasoningResult, ReasoningStep

# ──────────────────────────────────────────────────────────────
# REASONING TEMPLATES — One per problem type
# ──────────────────────────────────────────────────────────────

REASONING_TEMPLATES: dict[str, dict[str, Any]] = {
    "api": {
        "answer": (
            "Design a REST API with proper endpoints, request/response schemas, "
            "authentication middleware, and error handling. Use FastAPI for the "
            "framework and SQLite for persistence. Implement input validation "
            "with Pydantic models and add OpenAPI documentation."
        ),
        "steps": [
            {"desc": "Identify resources and map to endpoints", "conclusion": "Resources identified and endpoints mapped"},
            {"desc": "Define request/response schemas", "conclusion": "Schemas defined with validation rules"},
            {"desc": "Implement route handlers with error handling", "conclusion": "Routes implemented with proper HTTP status codes"},
        ],
        "confidence": 0.75,
    },
    "auth": {
        "answer": (
            "Implement JWT-based authentication with token refresh, password "
            "hashing (bcrypt/PBKDF2), RBAC for authorization, and API key support "
            "for service-to-service communication. Add rate limiting and account "
            "lockout after failed attempts."
        ),
        "steps": [
            {"desc": "Define auth mechanism and user model", "conclusion": "JWT auth selected with user model defined"},
            {"desc": "Implement credential verification and token generation", "conclusion": "Token generation and verification implemented"},
            {"desc": "Add authorization middleware with role-based access", "conclusion": "RBAC middleware implemented"},
        ],
        "confidence": 0.80,
    },
    "database": {
        "answer": (
            "Design a normalized database schema with proper foreign keys, indexes "
            "for query performance, parameterized queries for security, and "
            "migration scripts for schema evolution. Use SQLAlchemy ORM for "
            "abstraction and implement connection pooling."
        ),
        "steps": [
            {"desc": "Analyze data requirements and relationships", "conclusion": "Entity relationships mapped"},
            {"desc": "Design normalized schema with constraints", "conclusion": "Schema designed with proper normalization"},
            {"desc": "Implement CRUD with parameterized queries", "conclusion": "CRUD operations implemented safely"},
        ],
        "confidence": 0.78,
    },
    "invoice": {
        "answer": (
            "Build an invoice system with line items, tax calculation, discount "
            "support, PDF generation, and payment tracking. Use parameterized SQL "
            "for all database operations. Implement multi-currency support and "
            "sequential invoice numbering."
        ),
        "steps": [
            {"desc": "Define invoice model with line items and tax rules", "conclusion": "Invoice data model defined"},
            {"desc": "Implement subtotal, tax, and discount calculations", "conclusion": "Calculations implemented with precision handling"},
            {"desc": "Add validation and PDF export", "conclusion": "Validation and PDF generation ready"},
        ],
        "confidence": 0.82,
    },
    "inventory": {
        "answer": (
            "Create an inventory management system with stock tracking, low-stock "
            "alerts, movement history, and reporting. Implement CRUD operations "
            "with validation. Add batch operations and warehouse management."
        ),
        "steps": [
            {"desc": "Define product and movement data models", "conclusion": "Models defined with proper relationships"},
            {"desc": "Implement stock tracking with real-time updates", "conclusion": "Real-time stock levels implemented"},
            {"desc": "Add alerts, history, and reporting", "conclusion": "Alert system and reporting ready"},
        ],
        "confidence": 0.80,
    },
    "crm": {
        "answer": (
            "Develop a CRM with lead pipeline management, contact tracking, sales "
            "stage progression, and conversion analytics. Include email notification "
            "for stage changes and activity timeline for each contact."
        ),
        "steps": [
            {"desc": "Define pipeline stages and contact models", "conclusion": "Pipeline and contact models defined"},
            {"desc": "Implement stage progression with rules", "conclusion": "Stage progression logic implemented"},
            {"desc": "Add analytics and notifications", "conclusion": "Analytics dashboard and notifications ready"},
        ],
        "confidence": 0.77,
    },
    "automation": {
        "answer": (
            "Design an automation workflow with trigger detection, action execution, "
            "conditional logic, and error handling. Use APScheduler for scheduling "
            "and implement retry with exponential backoff for action execution."
        ),
        "steps": [
            {"desc": "Identify trigger type and action requirements", "conclusion": "Trigger and actions identified"},
            {"desc": "Design workflow with conditions and error handling", "conclusion": "Workflow designed with proper error recovery"},
            {"desc": "Implement execution engine with retry logic", "conclusion": "Execution engine ready with backoff retry"},
        ],
        "confidence": 0.73,
    },
    "logical": {
        "answer": (
            "Implement a rule evaluation engine with short-circuit logic, "
            "decision tree traversal, and conflict detection. Use boolean "
            "expression parsing and support AND/OR/NOT operators."
        ),
        "steps": [
            {"desc": "Identify conditions and map decision tree", "conclusion": "Decision tree mapped with all branches"},
            {"desc": "Implement rule evaluation with short-circuit", "conclusion": "Evaluation engine implemented"},
            {"desc": "Add validation for edge cases", "conclusion": "Edge cases handled and validated"},
        ],
        "confidence": 0.70,
    },
    "arithmetic": {
        "answer": (
            "Implement arithmetic computation with precision handling, formula "
            "evaluation, and result validation. Use decimal type for monetary "
            "calculations and add rounding rules per business requirements."
        ),
        "steps": [
            {"desc": "Identify calculations and input variables", "conclusion": "Variables and formulas identified"},
            {"desc": "Implement computations with precision", "conclusion": "Precision calculations implemented"},
            {"desc": "Add rounding and result validation", "conclusion": "Rounding rules and validation applied"},
        ],
        "confidence": 0.85,
    },
    "structural": {
        "answer": (
            "Refactor the codebase following established design patterns: extract "
            "interfaces, decouple modules, add dependency injection, and ensure "
            "each component has a single responsibility. Create incremental "
            "migration plan with regression tests."
        ),
        "steps": [
            {"desc": "Analyze current structure and identify improvements", "conclusion": "Structure analysis complete"},
            {"desc": "Design target architecture with module boundaries", "conclusion": "Target architecture designed"},
            {"desc": "Implement incremental refactoring with tests", "conclusion": "Refactoring done with regression safety"},
        ],
        "confidence": 0.65,
    },
}

# Generic template for unknown problem types
GENERIC_TEMPLATE: dict[str, Any] = {
    "answer": (
        "Based on analysis, this requires a structured implementation with: "
        "(1) Data models and validation, (2) Business logic with error handling, "
        "(3) API endpoints or automation workflows, (4) Tests for critical paths."
    ),
    "steps": [
        {"desc": "Analyze requirements and define scope", "conclusion": "Requirements analyzed and scope defined"},
        {"desc": "Design data models and interfaces", "conclusion": "Models and interfaces designed"},
        {"desc": "Implement core logic with error handling", "conclusion": "Core logic implemented"},
    ],
    "confidence": 0.40,
}


class TemplateReasoner(BaseAgent[ReasoningResult]):
    """
    A37: Apply template-based reasoning for known problem types.

    Single Responsibility: Template reasoning ONLY.
    Method: Lookup table by problem type (deterministic).
    Fallback: Return generic reasoning template.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A37_TemplateReasoner", **kwargs)

    def execute(self, input_data: Any) -> ReasoningResult:
        """
        Apply template-based reasoning.

        input_data can be:
          - ProblemType object (preferred — from A35)
          - DecomposedSteps object (from A36 — uses its context)
          - dict with 'problem_type' key (ProblemType or str)
          - dict with 'query' key (raw text, will auto-detect type)
          - str (raw query text)
        """
        problem_type = self._extract_problem_type(input_data)
        query = self._extract_query(input_data)
        context = self._extract_context(input_data)

        ptype_str = problem_type.type if problem_type else "general"

        # Look up template
        template = REASONING_TEMPLATES.get(ptype_str, GENERIC_TEMPLATE)

        # Build answer, enriching with context if available
        answer = template["answer"]
        if context:
            answer = f"{answer} | Additional context: {context[:200]}"

        # Build reasoning steps from template
        steps = self._build_steps(template)

        # Compute confidence (may adjust based on template match)
        confidence = template["confidence"]
        if ptype_str == "general":
            confidence = GENERIC_TEMPLATE["confidence"]

        # Track which template was used
        template_used = ptype_str if ptype_str in REASONING_TEMPLATES else "generic"

        return ReasoningResult(
            answer=answer,
            template_used=template_used,
            confidence=confidence,
            steps=steps,
            source="deterministic",
        )

    def _extract_problem_type(self, input_data: Any) -> Optional[ProblemType]:
        """Extract ProblemType from input."""
        if isinstance(input_data, ProblemType):
            return input_data
        elif isinstance(input_data, dict):
            pt = input_data.get("problem_type")
            if isinstance(pt, ProblemType):
                return pt
            elif isinstance(pt, str):
                return ProblemType(type=pt)
            if "type" in input_data and isinstance(input_data["type"], str):
                return ProblemType(type=input_data["type"])
        return None

    def _extract_query(self, input_data: Any) -> str:
        """Extract query text from input."""
        if isinstance(input_data, str):
            return input_data
        elif isinstance(input_data, dict):
            return input_data.get("query", input_data.get("text", input_data.get("description", "")))
        for attr in ("query", "text", "description"):
            if hasattr(input_data, attr):
                return getattr(input_data, attr, "")
        return ""

    def _extract_context(self, input_data: Any) -> str:
        """Extract additional context string from input."""
        if isinstance(input_data, dict):
            return input_data.get("context", "")
        if hasattr(input_data, "context"):
            return getattr(input_data, "context", "")
        return ""

    def _build_steps(self, template: dict[str, Any]) -> list[ReasoningStep]:
        """Build ReasoningStep list from template."""
        steps: list[ReasoningStep] = []
        for i, step_data in enumerate(template.get("steps", [])):
            steps.append(ReasoningStep(
                step_number=i + 1,
                description=step_data.get("desc", ""),
                conclusion=step_data.get("conclusion", ""),
                confidence=template.get("confidence", 0.5),
            ))
        return steps

    def list_available_templates(self) -> list[str]:
        """List all available reasoning template names."""
        return list(REASONING_TEMPLATES.keys())

    def fallback(self, input_data: Any) -> ReasoningResult:
        """Fallback: Return generic reasoning template."""
        steps = self._build_steps(GENERIC_TEMPLATE)
        return ReasoningResult(
            answer=GENERIC_TEMPLATE["answer"],
            template_used="generic",
            confidence=GENERIC_TEMPLATE["confidence"],
            steps=steps,
            source="fallback",
        )
