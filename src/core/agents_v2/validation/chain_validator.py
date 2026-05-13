"""
A25 ChainValidator — SINGLE RESPONSIBILITY: Validate logic chain compatibility and completeness.

Deterministic. No AI.
Validates:
  1. Block structure (names, execute methods, categories)
  2. Type compatibility between consecutive blocks (output→input)
  3. Category-specific rules (auth needs db, data needs db, integrations need data)
  4. Chain completeness (no missing required blocks)
  5. Performance hints for long chains
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..resilience import BaseAgent
from ..schemas import ChainResult, ValidationIssue

# ──────────────────────────────────────────────────────────────
# COMPATIBILITY RULES — Between block categories
# ──────────────────────────────────────────────────────────────

CHAIN_COMPATIBILITY_RULES: dict[tuple, str] = {
    ("data", "validation"): "good",
    ("validation", "data"): "good",
    ("data", "business_logic"): "good",
    ("validation", "business_logic"): "warning",
    ("business_logic", "validation"): "warning",
    ("auth", "data"): "good",
    ("auth", "business_logic"): "warning",
    ("integrations", "business_logic"): "warning",
    ("business_logic", "integrations"): "good",
    ("data", "data"): "warning",  # Redundant data blocks
}

# Categories that require specific context
CATEGORY_CONTEXT_REQUIREMENTS: dict[str, list[str]] = {
    "auth": ["db"],
    "data": ["db"],
    "integrations": ["data_fields"],
}

# Categories that require specific initial data
CATEGORY_DATA_REQUIREMENTS: dict[str, dict[str, str]] = {
    "integrations": {"email": "to"},
}


class ChainValidator(BaseAgent[ChainResult]):
    """
    A25: Validate logic chain compatibility and completeness.

    Single Responsibility: Chain validation ONLY.
    Method: Structural + type compatibility checks (deterministic).
    Fallback: Return valid=True (trust when cannot parse).
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A25_ChainValidator", **kwargs)

    def execute(self, input_data: Any) -> ChainResult:
        """
        Validate a logic chain.

        input_data should be a dict with:
          - 'chain': The chain to validate (dict, list, JSON string, or object with blocks)
          - 'context': Optional dict with execution context (e.g., {'db': True})
          - 'initial_data': Optional dict with data that will be passed to execute()
          - 'strict': Optional bool for strict validation (default: False)
        """
        if not isinstance(input_data, dict):
            return self.fallback(input_data)

        chain_data = input_data.get("chain", input_data)
        context = input_data.get("context", {})
        initial_data = input_data.get("initial_data", {})
        strict = input_data.get("strict", False)

        # Parse chain into a uniform format
        blocks = self._parse_chain(chain_data)
        if blocks is None:
            return ChainResult(
                valid=True,
                incompatibilities=[],
                missing=[],
                source="deterministic",
            )

        incompatibilities: list[str] = []
        missing: list[str] = []

        # 1. Empty chain check
        if not blocks:
            return ChainResult(
                valid=True,
                incompatibilities=[],
                missing=["blocks"],
                source="deterministic",
            )

        # 2. Validate each block's structure
        block_issues = self._validate_block_structure(blocks, context, initial_data)
        incompatibilities.extend(block_issues)

        # 3. Type compatibility between consecutive blocks
        type_issues = self._validate_type_compatibility(blocks)
        incompatibilities.extend(type_issues)

        # 4. Category compatibility rules
        category_issues = self._validate_category_compatibility(blocks)
        incompatibilities.extend(category_issues)

        # 5. Check for missing required elements
        missing_items = self._check_missing_requirements(blocks, context, initial_data)
        missing.extend(missing_items)

        # 6. Strict mode additional checks
        if strict:
            strict_issues = self._validate_strict(blocks, incompatibilities)
            incompatibilities.extend(strict_issues)

        # Determine overall validity
        # valid=False only if there are critical incompatibilities
        critical_issues = [i for i in incompatibilities if i.startswith("CRITICAL:")]
        valid = len(critical_issues) == 0

        return ChainResult(
            valid=valid,
            incompatibilities=incompatibilities,
            missing=missing,
            source="deterministic",
        )

    def _parse_chain(self, chain_data: Any) -> Optional[list[Any]]:
        """Parse chain data into a list of blocks."""
        if isinstance(chain_data, str):
            try:
                parsed = json.loads(chain_data)
                return parsed.get("blocks", []) if isinstance(parsed, dict) else parsed
            except (json.JSONDecodeError, TypeError):
                return None
        elif isinstance(chain_data, dict):
            return chain_data.get("blocks", [])
        elif isinstance(chain_data, list):
            return chain_data
        elif hasattr(chain_data, "blocks"):
            return chain_data.blocks
        elif hasattr(chain_data, "_blocks"):
            return chain_data._blocks
        return None

    def _validate_block_structure(
        self,
        blocks: list[Any],
        context: dict[str, Any],
        initial_data: dict[str, Any],
    ) -> list[str]:
        """Validate individual block structure and requirements."""
        issues = []

        for i, block in enumerate(blocks):
            block_dict = block if isinstance(block, dict) else {}
            block_name = (
                block_dict.get("name", None)
                if isinstance(block, dict)
                else getattr(block, "name", None)
            )
            if not block_name:
                issues.append(f"Block at index {i} has no name")

            # Check for execute method on object blocks
            if not isinstance(block, dict) and not hasattr(block, "execute"):
                issues.append(
                    f"CRITICAL: Block '{block_name or f'block_{i}'}' has no execute method"
                )

            # Check category
            category = self._get_block_category(block)
            if not category:
                continue

            # Category-specific context requirements
            required_ctx = CATEGORY_CONTEXT_REQUIREMENTS.get(category, [])
            for req in required_ctx:
                if req not in context:
                    issues.append(
                        f"Block '{block_name or f'block_{i}'}' ({category}) "
                        f"may need '{req}' in context"
                    )

            # Category-specific data requirements
            data_reqs = CATEGORY_DATA_REQUIREMENTS.get(category, {})
            for block_type, req_field in data_reqs.items():
                if block_name and block_name.startswith(block_type):
                    if req_field not in initial_data:
                        issues.append(
                            f"Block '{block_name}' ({category}) needs "
                            f"'{req_field}' in initial data"
                        )

        return issues

    def _validate_type_compatibility(self, blocks: list[Any]) -> list[str]:
        """Check that block outputs can feed into subsequent block inputs."""
        issues = []

        for i in range(len(blocks) - 1):
            current = blocks[i]
            next_block = blocks[i + 1]

            if not self._check_type_compatibility(current, next_block):
                current_name = (
                    current.get("name", f"block_{i}")
                    if isinstance(current, dict)
                    else getattr(current, "name", f"block_{i}")
                )
                next_name = (
                    next_block.get("name", f"block_{i+1}")
                    if isinstance(next_block, dict)
                    else getattr(next_block, "name", f"block_{i+1}")
                )
                issues.append(
                    f"Type mismatch: '{current_name}' outputs incompatible "
                    f"with '{next_name}' inputs"
                )

        return issues

    @staticmethod
    def _check_type_compatibility(block: Any, next_block: Any) -> bool:
        """Check that block outputs are compatible with next_block inputs."""
        outputs = getattr(block, "outputs", None) or []
        inputs = getattr(next_block, "inputs", None) or []

        # Also check dict-style blocks
        if isinstance(block, dict):
            outputs = block.get("outputs", outputs)
        if isinstance(next_block, dict):
            inputs = next_block.get("inputs", inputs)

        # If no type information, assume compatible
        if not outputs or not inputs:
            return True

        # Normalize types to sets of strings
        output_types: set[str] = set()
        for o in outputs:
            output_types.add(o if isinstance(o, str) else o.get("type", ""))

        input_types: set[str] = set()
        for inp in inputs:
            input_types.add(inp if isinstance(inp, str) else inp.get("type", ""))

        # Empty type info → compatible
        if not output_types or not input_types:
            return True

        # Check for intersection or 'any' wildcard
        common = output_types & input_types
        if common or "any" in output_types or "any" in input_types:
            return True

        return False

    def _validate_category_compatibility(self, blocks: list[Any]) -> list[str]:
        """Check category-level compatibility between consecutive blocks."""
        issues = []

        for i in range(len(blocks) - 1):
            current_cat = self._get_block_category(blocks[i])
            next_cat = self._get_block_category(blocks[i + 1])

            if not current_cat or not next_cat:
                continue

            rule = CHAIN_COMPATIBILITY_RULES.get((current_cat, next_cat))
            if rule == "warning":
                issues.append(
                    f"Category hint: {current_cat} → {next_cat} at step {i}-{i+1}: "
                    f"consider reordering"
                )

        return issues

    def _check_missing_requirements(
        self,
        blocks: list[Any],
        context: dict[str, Any],
        initial_data: dict[str, Any],
    ) -> list[str]:
        """Check for missing required elements in the chain."""
        missing = []

        # Check if chain has auth operations but no auth block
        has_auth_context = bool(context.get("auth_required"))
        has_auth_block = any(
            self._get_block_category(b) == "auth" for b in blocks
        )
        if has_auth_context and not has_auth_block:
            missing.append("auth_block")

        # Check if chain has database operations but no data block
        has_db_context = bool(context.get("db"))
        has_data_block = any(
            self._get_block_category(b) == "data" for b in blocks
        )
        if has_db_context and not has_data_block:
            missing.append("data_block")

        return missing

    def _validate_strict(
        self,
        blocks: list[Any],
        existing_issues: list[str],
    ) -> list[str]:
        """Strict mode: additional validation checks."""
        issues = []

        # Long chain warning
        if len(blocks) > 10:
            issues.append(
                f"Chain has {len(blocks)} blocks — consider splitting into sub-chains"
            )

        # Duplicate block names
        names = []
        for block in blocks:
            if isinstance(block, dict):
                names.append(block.get("name", ""))
            else:
                names.append(getattr(block, "name", ""))
        seen = set()
        for name in names:
            if name and name in seen:
                issues.append(
                    f"Duplicate block name '{name}' — verify this is intentional"
                )
            seen.add(name)

        # Check that validation comes before business logic
        categories = [self._get_block_category(b) for b in blocks]
        for i in range(len(categories) - 1):
            if categories[i] == "business_logic" and categories[i + 1] == "validation":
                issues.append(
                    f"Validation after business logic at step {i+1} — "
                    f"consider validating first"
                )

        return issues

    @staticmethod
    def _get_block_category(block: Any) -> str:
        """Extract category from a block (dict or object)."""
        if isinstance(block, dict):
            return block.get("category", block.get("type", ""))
        return getattr(block, "category", getattr(block, "type", ""))

    def fallback(self, input_data: Any) -> ChainResult:
        """
        Fallback: Return valid=True.
        When chain cannot be parsed, we trust by default.
        The VerdictEngine will still catch issues at the consensus level.
        """
        return ChainResult(valid=True, source="fallback")
