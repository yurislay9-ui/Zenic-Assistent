"""
ZENIC-AGENTS — Policy Condition Evaluator

PolicyCondition dataclass with condition evaluation logic.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List

from ._types import ConditionOperator

logger = logging.getLogger(__name__)

# Sentinel for missing values in dict navigation
_SENTINEL = object()


@dataclass
class PolicyCondition:
    """A condition that determines when a policy rule applies.

    The `field` uses dot-notation to navigate nested dicts:
      - "config.amount" → context["config"]["amount"]
      - "action_type"   → evaluated directly on the action_type string

    Supported operators: eq, neq, gt, lt, gte, lte, contains, in, regex.
    """
    field: str
    operator: ConditionOperator
    value: Any = None

    def evaluate(
        self,
        action_type: str,
        config: Dict[str, Any],
        context: Dict[str, Any],
    ) -> bool:
        """Evaluate this condition against the given action/config/context.

        Args:
            action_type: The action type string.
            config: The action configuration dict.
            context: The context dict.

        Returns:
            True if the condition matches, False otherwise.
        """
        actual = self._resolve_field(action_type, config, context)
        return self._compare(actual, self.value)

    def _resolve_field(
        self,
        action_type: str,
        config: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Any:
        """Resolve the field path to an actual value.

        Supports:
          - "action_type" → the action_type string
          - "config.xxx" → config["xxx"]
          - "context.xxx" → context["xxx"]
          - "config.nested.key" → config["nested"]["key"]
        """
        parts = self.field.split(".")
        if parts[0] == "action_type":
            return action_type
        elif parts[0] == "config" and len(parts) > 1:
            return self._navigate(config, parts[1:])
        elif parts[0] == "context" and len(parts) > 1:
            return self._navigate(context, parts[1:])
        # Fallback: try config first, then context
        val = self._navigate(config, parts)
        if val is _SENTINEL:
            val = self._navigate(context, parts)
        return val if val is not _SENTINEL else None

    @staticmethod
    def _navigate(obj: Any, keys: List[str]) -> Any:
        """Navigate nested dicts using a list of keys."""
        current = obj
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return _SENTINEL
        return current

    def _compare(self, actual: Any, expected: Any) -> bool:
        """Compare actual value to expected using the configured operator."""
        op = self.operator

        if op == ConditionOperator.EQ:
            return actual == expected

        if op == ConditionOperator.NEQ:
            return actual != expected

        if op == ConditionOperator.GT:
            try:
                return float(actual) > float(expected)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return False

        if op == ConditionOperator.LT:
            try:
                return float(actual) < float(expected)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return False

        if op == ConditionOperator.GTE:
            try:
                return float(actual) >= float(expected)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return False

        if op == ConditionOperator.LTE:
            try:
                return float(actual) <= float(expected)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return False

        if op == ConditionOperator.CONTAINS:
            if isinstance(actual, str) and isinstance(expected, str):
                return expected in actual
            if isinstance(actual, (list, tuple)):
                return expected in actual
            return False

        if op == ConditionOperator.IN:
            if isinstance(expected, (list, tuple, set)):
                return actual in expected
            if isinstance(actual, str) and isinstance(expected, str):
                return actual in expected
            return False

        if op == ConditionOperator.NOT_IN:
            if isinstance(expected, (list, tuple, set)):
                return actual not in expected
            return True

        if op == ConditionOperator.STARTS_WITH:
            if isinstance(actual, str) and isinstance(expected, str):
                return actual.startswith(expected)
            return False

        if op == ConditionOperator.ENDS_WITH:
            if isinstance(actual, str) and isinstance(expected, str):
                return actual.endswith(expected)
            return False

        if op == ConditionOperator.EXISTS:
            return actual is not None and actual is not _SENTINEL

        if op == ConditionOperator.NOT_EXISTS:
            return actual is None or actual is _SENTINEL

        if op == ConditionOperator.REGEX:
            try:
                return bool(re.search(str(expected), str(actual)))
            except re.error:
                logger.warning(
                    "PolicyCondition: Invalid regex pattern '%s'", expected,
                )
                return False

        # Unknown operator — condition does not match
        logger.warning("PolicyCondition: Unknown operator '%s'", op)
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "field": self.field,
            "operator": self.operator.value,
            "value": self.value,
        }
