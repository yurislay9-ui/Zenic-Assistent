"""
A36 StepDecomposer — SINGLE RESPONSIBILITY: Break a problem into ordered reasoning steps.

Deterministic decomposition based on problem type. No AI.
Each step has a number, description, and optional conclusion.
Steps have explicit dependencies and a topological execution order.

Ported from:
  - ReasoningEngine.step_by_step() (reasoning_parts/_step_mixin.py)
  - ReasoningEngine._fallback_step() (reasoning_parts/_helpers_mixin.py)
  - ThinkingEngine._fallback_decompose() (thinking_parts/_reasoning_mixin.py)
"""

from __future__ import annotations

from typing import Any, Optional

from ..resilience import BaseAgent
from ..schemas import DecomposedSteps, ProblemType, ReasoningStep

# ──────────────────────────────────────────────────────────────
# STEP TEMPLATES PER PROBLEM TYPE
# ──────────────────────────────────────────────────────────────

# Each template is a list of (description, depends_on) tuples
STEP_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "api": [
        {"desc": "Identify API endpoints and resource models", "depends": []},
        {"desc": "Design request/response schemas for each endpoint", "depends": ["step_1"]},
        {"desc": "Implement API route handlers with validation", "depends": ["step_2"]},
        {"desc": "Add error handling and HTTP status codes", "depends": ["step_3"]},
        {"desc": "Write integration tests for critical paths", "depends": ["step_3"]},
    ],
    "auth": [
        {"desc": "Define authentication mechanism and user model", "depends": []},
        {"desc": "Implement credential verification and token generation", "depends": ["step_1"]},
        {"desc": "Add authorization middleware and role checks", "depends": ["step_2"]},
        {"desc": "Implement session management and token refresh", "depends": ["step_2"]},
        {"desc": "Security audit for common auth vulnerabilities", "depends": ["step_3", "step_4"]},
    ],
    "database": [
        {"desc": "Analyze data requirements and define entity relationships", "depends": []},
        {"desc": "Design normalized database schema with proper constraints", "depends": ["step_1"]},
        {"desc": "Create migration scripts and seed data", "depends": ["step_2"]},
        {"desc": "Implement CRUD operations with parameterized queries", "depends": ["step_2"]},
        {"desc": "Add indexes for query performance optimization", "depends": ["step_4"]},
    ],
    "invoice": [
        {"desc": "Define invoice data model with line items and tax rules", "depends": []},
        {"desc": "Implement subtotal, tax, and discount calculations", "depends": ["step_1"]},
        {"desc": "Add validation for amounts, dates, and required fields", "depends": ["step_2"]},
        {"desc": "Implement invoice generation and PDF export", "depends": ["step_2"]},
        {"desc": "Add payment tracking and status management", "depends": ["step_3", "step_4"]},
    ],
    "inventory": [
        {"desc": "Define product and stock movement data models", "depends": []},
        {"desc": "Implement stock tracking with real-time level updates", "depends": ["step_1"]},
        {"desc": "Add low-stock alerts and reorder point logic", "depends": ["step_2"]},
        {"desc": "Implement movement history and audit trail", "depends": ["step_2"]},
        {"desc": "Add reporting for stock levels and movement summaries", "depends": ["step_3", "step_4"]},
    ],
    "crm": [
        {"desc": "Define pipeline stages and contact data models", "depends": []},
        {"desc": "Implement stage progression with validation rules", "depends": ["step_1"]},
        {"desc": "Add conversion tracking and forecasting logic", "depends": ["step_2"]},
        {"desc": "Implement notification triggers for stage changes", "depends": ["step_2"]},
        {"desc": "Add reporting for pipeline analytics and metrics", "depends": ["step_3"]},
    ],
    "automation": [
        {"desc": "Identify trigger type and action requirements", "depends": []},
        {"desc": "Design workflow with conditional logic and error handling", "depends": ["step_1"]},
        {"desc": "Implement action execution with retry and rollback", "depends": ["step_2"]},
        {"desc": "Add scheduling and event subscription", "depends": ["step_2"]},
        {"desc": "Create monitoring and audit logging for automation runs", "depends": ["step_3", "step_4"]},
    ],
    "logical": [
        {"desc": "Identify conditions and decision rules", "depends": []},
        {"desc": "Map decision tree with all possible branches", "depends": ["step_1"]},
        {"desc": "Implement rule evaluation engine with short-circuit logic", "depends": ["step_2"]},
        {"desc": "Add validation for edge cases and conflicting rules", "depends": ["step_3"]},
    ],
    "arithmetic": [
        {"desc": "Identify required calculations and input variables", "depends": []},
        {"desc": "Define formulas and computation order", "depends": ["step_1"]},
        {"desc": "Implement calculations with precision handling", "depends": ["step_2"]},
        {"desc": "Add rounding rules and result validation", "depends": ["step_3"]},
    ],
    "structural": [
        {"desc": "Analyze current structure and identify improvement areas", "depends": []},
        {"desc": "Design target architecture with clear module boundaries", "depends": ["step_1"]},
        {"desc": "Create migration plan with incremental refactoring steps", "depends": ["step_2"]},
        {"desc": "Implement structural changes with regression safety", "depends": ["step_3"]},
    ],
}

# Default generic template when no type matches
GENERIC_TEMPLATE: list[dict[str, Any]] = [
    {"desc": "Analyze requirements and define scope", "depends": []},
    {"desc": "Design data models and interfaces", "depends": ["step_1"]},
    {"desc": "Implement core logic with error handling", "depends": ["step_2"]},
    {"desc": "Add input validation and edge case handling", "depends": ["step_3"]},
    {"desc": "Create test cases for critical paths", "depends": ["step_3"]},
]

# Maximum number of reasoning steps (safety limit)
MAX_STEPS = 8


class StepDecomposer(BaseAgent[DecomposedSteps]):
    """
    A36: Break a problem into ordered reasoning steps.

    Single Responsibility: Step decomposition ONLY.
    Method: Template-based decomposition by problem type (deterministic).
    Fallback: Return generic 3-step process.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A36_StepDecomposer", **kwargs)

    def execute(self, input_data: Any) -> DecomposedSteps:
        """
        Decompose a problem into ordered reasoning steps.

        input_data can be:
          - ProblemType object (preferred — from A35)
          - dict with 'problem_type' key (ProblemType or str)
          - dict with 'query' key (raw text, will be auto-detected)
          - str (raw query text)
        """
        problem_type = self._extract_problem_type(input_data)
        query = self._extract_query(input_data)

        # Get the appropriate step template
        template = STEP_TEMPLATES.get(
            problem_type.type if problem_type else "general",
            GENERIC_TEMPLATE,
        )

        # Build reasoning steps from template
        steps = self._build_steps(template, query)

        # Compute dependencies and topological order
        dependencies = self._extract_dependencies(template)
        order = self._compute_order(steps)

        return DecomposedSteps(
            steps=steps[:MAX_STEPS],
            dependencies=dependencies,
            order=order,
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
            # Check for type key directly
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

    def _build_steps(
        self, template: list[dict[str, Any]], query: str
    ) -> list[ReasoningStep]:
        """Build ReasoningStep list from template."""
        steps: list[ReasoningStep] = []
        for i, tmpl in enumerate(template[:MAX_STEPS]):
            # Enrich step description with query context if available
            desc = tmpl.get("desc", f"Step {i + 1}")
            if query and i == 0:
                desc = f"{desc} [context: {query[:80]}]"

            steps.append(ReasoningStep(
                step_number=i + 1,
                description=desc,
                conclusion="",
                confidence=0.0,  # Not yet executed
            ))
        return steps

    def _extract_dependencies(self, template: list[dict[str, Any]]) -> list[str]:
        """Extract dependency strings from template."""
        deps: list[str] = []
        for i, tmpl in enumerate(template[:MAX_STEPS]):
            for dep in tmpl.get("depends", []):
                deps.append(f"step_{i + 1} depends on {dep}")
        return deps

    def _compute_order(self, steps: list[ReasoningStep]) -> list[int]:
        """Compute topological execution order (sequential by default)."""
        return [s.step_number for s in steps]

    def decompose_with_context(
        self, input_data: Any, context: str = ""
    ) -> DecomposedSteps:
        """
        Decompose with additional context injected into step descriptions.

        This is the deterministic equivalent of the original
        step_by_step() method that injected memory context.
        """
        result = self.execute(input_data)

        if context and result.steps:
            # Inject context into the first step
            first = result.steps[0]
            enriched_desc = f"{first.description} | Context: {context[:200]}"
            result.steps[0] = ReasoningStep(
                step_number=first.step_number,
                description=enriched_desc,
                conclusion=first.conclusion,
                confidence=first.confidence,
            )

        return result

    def fallback(self, input_data: Any) -> DecomposedSteps:
        """Fallback: Return generic 3-step decomposition."""
        steps = [
            ReasoningStep(step_number=1, description="Analyze the problem"),
            ReasoningStep(step_number=2, description="Apply standard patterns"),
            ReasoningStep(step_number=3, description="Verify the result"),
        ]
        return DecomposedSteps(
            steps=steps,
            dependencies=["step_2 depends on step_1", "step_3 depends on step_2"],
            order=[1, 2, 3],
            source="fallback",
        )
