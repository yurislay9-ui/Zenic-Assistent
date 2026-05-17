"""
A32 ConditionExtractor — SINGLE RESPONSIBILITY: Extract conditional logic from description.

Deterministic regex + keyword matching. No AI.
Extracts conditions from "if/when/si/cuando" clauses in natural
language descriptions (EN + ES bilingual) and builds a simple logic tree.
"""

from __future__ import annotations

import re
from typing import Any

from ..resilience import BaseAgent
from ..schemas import AutoDescription, ConditionResult

# ──────────────────────────────────────────────────────────────
# CONDITION PATTERNS — EN + ES bilingual
# ──────────────────────────────────────────────────────────────

# Patterns that introduce conditions
# Key fix: use (?:,|\.|$) as terminators, not requiring them after every match
CONDITION_INTRODUCERS = [
    # Spanish — "si" must be word boundary to avoid matching inside other words
    r"\bsi\s+(.+?)(?:,|\.|$)",
    r"\bsolo si\s+(.+?)(?:,|\.|$)",
    r"\bsolo cuando\s+(.+?)(?:,|\.|$)",
    r"\bcuando\s+(.+?)(?:,|\.|$)",
    r"\bsiempre que\s+(.+?)(?:,|\.|$)",
    r"\ben caso de que\s+(.+?)(?:,|\.|$)",
    # English
    r"\bif\s+(.+?)(?:,|\.|$)",
    r"\bonly when\s+(.+?)(?:,|\.|$)",
    r"\bonly if\s+(.+?)(?:,|\.|$)",
    r"\bwhen\s+(.+?)(?:,|\.|$)",
    r"\bwhenever\s+(.+?)(?:,|\.|$)",
    r"\bin case\s+(.+?)(?:,|\.|$)",
    r"\bprovided that\s+(.+?)(?:,|\.|$)",
]

# Logical operators
AND_PATTERNS = [" y ", " and ", " & ", " además ", " también "]
OR_PATTERNS = [" o ", " or ", " | ", " sino también "]
NOT_PATTERNS = [" no ", " not ", " excepto ", " unless ", " menos "]


class ConditionExtractor(BaseAgent[ConditionResult]):
    """
    A32: Extract conditional logic from automation description.

    Single Responsibility: Condition extraction ONLY.
    Method: Regex + keyword pattern matching (deterministic).
    Fallback: Return empty conditions (no conditions = always execute).
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A32_ConditionExtractor", **kwargs)
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in CONDITION_INTRODUCERS  # nosemgrep: detect-non-literal-regexp
        ]

    def execute(self, input_data: Any) -> ConditionResult:
        """
        Extract conditions from description.

        input_data can be:
          - AutoDescription object
          - dict with 'description' key
          - str (the description itself)
        """
        description = self._extract_description(input_data)

        if not description:
            return ConditionResult(
                conditions=[],
                logic_tree={},
                source="deterministic",
            )

        # 1. Extract condition clauses
        raw_conditions = self._extract_condition_clauses(description)

        if not raw_conditions:
            return ConditionResult(
                conditions=[],
                logic_tree={},
                source="deterministic",
            )

        # 2. Parse each clause into structured conditions
        conditions = []
        for clause in raw_conditions:
            parsed = self._parse_condition_clause(clause)
            if parsed:
                conditions.append(parsed)

        # 3. Build logic tree
        logic_tree = self._build_logic_tree(conditions, description)

        return ConditionResult(
            conditions=conditions,
            logic_tree=logic_tree,
            source="deterministic",
        )

    def _extract_description(self, input_data: Any) -> str:
        """Extract description from various input formats."""
        if isinstance(input_data, AutoDescription):
            return input_data.description
        elif isinstance(input_data, dict):
            return input_data.get("description", "")
        elif isinstance(input_data, str):
            return input_data
        return ""

    def _extract_condition_clauses(self, description: str) -> list[str]:
        """Extract raw condition clauses using regex patterns."""
        clauses = []
        seen = set()

        for pattern in self._compiled_patterns:
            matches = pattern.finditer(description)
            for match in matches:
                clause = match.group(1).strip()
                # Normalize and deduplicate
                clause_key = clause.lower()[:50]
                if clause_key not in seen and len(clause) > 2:
                    clauses.append(clause[:100])  # Cap length
                    seen.add(clause_key)

        return clauses

    def _parse_condition_clause(self, clause: str) -> str:
        """Parse a raw clause into a clean condition string."""
        # Clean trailing punctuation
        condition = clause.rstrip(".,;:!?")
        condition = condition.strip()

        # Ensure not empty after cleaning
        if len(condition) < 2:
            return ""

        return condition

    def _build_logic_tree(
        self, conditions: list[str], description: str
    ) -> dict[str, Any]:
        """
        Build a simple logic tree from conditions and description.

        Structure:
        {
            "operator": "AND" | "OR" | "SINGLE",
            "conditions": [...],
            "negated": bool,
        }
        """
        if not conditions:
            return {}

        # Detect logical operators in description
        desc_lower = description.lower()
        has_and = any(p in desc_lower for p in AND_PATTERNS)
        has_or = any(p in desc_lower for p in OR_PATTERNS)
        has_not = any(p in desc_lower for p in NOT_PATTERNS)

        # Determine primary operator
        if len(conditions) == 1:
            operator = "SINGLE"
        elif has_or and not has_and:
            operator = "OR"
        else:
            operator = "AND"  # Default: AND (all conditions must be met)

        return {
            "operator": operator,
            "conditions": conditions,
            "negated": has_not,
        }

    def fallback(self, input_data: Any) -> ConditionResult:
        """Fallback: Return empty conditions (always execute)."""
        return ConditionResult(
            conditions=[],
            logic_tree={},
            source="fallback",
        )
