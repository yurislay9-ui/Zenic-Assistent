"""
ZENIC-AGENTS - Policy-as-Code Engine (A2: Pre-action Validation Enhancement)

Declarative policy engine with Python-native rules (not OPA/Rego).

Policies are evaluated in priority order (higher = evaluated first).
The first DENY wins absolutely. REQUIRE_APPROVAL / ESCALATE win over
ALLOW. If no policy matches, the default is ALLOW.

Supports loading policies from:
  - YAML files (via load_policies_from_yaml)
  - Python dicts (via load_policies_from_dict)
  - Programmatic addition (via add_policy)

Thread-safe: All public methods guarded by RLock.
Singleton pattern: get_policy_engine() / reset_policy_engine().
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  ENUMS
# ──────────────────────────────────────────────────────────────

class PolicyAction(str, Enum):
    """Action that a policy rule prescribes when its condition matches."""
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
    ESCALATE = "ESCALATE"


class ConditionOperator(str, Enum):
    """Supported condition operators for policy evaluation.

    Canonical source of truth — policy_code.types imports from here.
    """
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"       # Added for parity with TypeScript/Rust
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"  # Added for parity with TypeScript/Rust
    ENDS_WITH = "ends_with"      # Added for parity with TypeScript/Rust
    REGEX = "regex"
    EXISTS = "exists"            # Added for parity with TypeScript/Rust
    NOT_EXISTS = "not_exists"    # Added for parity with TypeScript/Rust


# ──────────────────────────────────────────────────────────────
#  DATACLASSES
# ──────────────────────────────────────────────────────────────

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


# Sentinel for missing values in dict navigation
_SENTINEL = object()


@dataclass
class PolicyRule:
    """A single policy rule with a condition, action, and priority.

    When the condition matches, the rule's action is applied.
    Higher priority rules are evaluated first.

    Fields:
        name: Human-readable name of the policy rule.
        description: What the policy does.
        condition: When this policy applies (PolicyCondition).
        action: What to do when condition matches (ALLOW/DENY/etc.).
        priority: Higher = evaluated first. Default 0.
        escalation_role: Role required for ESCALATE action.
        category_filter: If set, only applies to actions in this category.
    """
    name: str
    description: str = ""
    condition: Optional[PolicyCondition] = None
    action: PolicyAction = PolicyAction.ALLOW
    priority: int = 0
    escalation_role: str = ""
    category_filter: str = ""

    def matches(
        self,
        action_type: str,
        config: Dict[str, Any],
        context: Dict[str, Any],
        category: str = "",
    ) -> bool:
        """Check if this policy rule matches the given action.

        Args:
            action_type: The action type string.
            config: The action configuration dict.
            context: The context dict.
            category: Optional category string to filter on.

        Returns:
            True if the rule's condition matches and category filter passes.
        """
        # Category filter check
        if self.category_filter and category:
            if self.category_filter.lower() != category.lower():
                return False

        # Condition check
        if self.condition is None:
            # No condition = always matches (within category)
            return True

        return self.condition.evaluate(action_type, config, context)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "condition": self.condition.to_dict() if self.condition else None,
            "action": self.action.value,
            "priority": self.priority,
            "escalation_role": self.escalation_role,
            "category_filter": self.category_filter,
        }


@dataclass
class PolicyDecision:
    """Result of evaluating all policies for an action.

    Contains the final decision action, which matched policies contributed,
    and the reasoning chain.
    """
    action: PolicyAction
    action_type: str
    matched_rules: List[str] = field(default_factory=list)
    denial_reason: str = ""
    escalation_role: str = ""
    requires_approval: bool = False
    requires_confirmation: bool = False
    evaluation_count: int = 0
    details: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        """Whether the action is allowed to proceed."""
        return self.action in (
            PolicyAction.ALLOW,
            PolicyAction.REQUIRE_APPROVAL,
            PolicyAction.REQUIRE_CONFIRMATION,
            PolicyAction.ESCALATE,
        )

    @property
    def denied(self) -> bool:
        """Whether the action is absolutely denied."""
        return self.action == PolicyAction.DENY

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "action": self.action.value,
            "action_type": self.action_type,
            "allowed": self.allowed,
            "denied": self.denied,
            "matched_rules": self.matched_rules,
            "denial_reason": self.denial_reason,
            "escalation_role": self.escalation_role,
            "requires_approval": self.requires_approval,
            "requires_confirmation": self.requires_confirmation,
            "evaluation_count": self.evaluation_count,
            "details": self.details,
        }


# ──────────────────────────────────────────────────────────────
#  POLICY ENGINE
# ──────────────────────────────────────────────────────────────

class PolicyEngine:
    """Policy-as-code engine with declarative rules.

    Evaluation order:
      1. Sort all policies by priority (higher = evaluated first).
      2. Evaluate each policy's condition against the action.
      3. First DENY wins — immediately returns a denial decision.
      4. First REQUIRE_APPROVAL / ESCALATE wins over ALLOW.
      5. If no matching policy, default is ALLOW.

    Thread-safe: All public methods guarded by RLock.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._policies: Dict[str, PolicyRule] = {}  # name -> rule
        self._eval_count: int = 0

    # ── Loading Policies ──────────────────────────────────

    def load_policies_from_yaml(self, yaml_path: str) -> int:
        """Load policy rules from a YAML file.

        Expected format:
          policies:
            - name: financial_approval
              description: "Financial actions > $10K require CFO"
              condition:
                field: config.amount
                operator: gt
                value: 10000
              action: REQUIRE_APPROVAL
              escalation_role: cfo
              category_filter: financial
              priority: 100

        Args:
            yaml_path: Path to the YAML file.

        Returns:
            Number of policies loaded.

        Raises:
            FileNotFoundError: If the YAML file does not exist.
            ValueError: If the YAML content is malformed.
        """
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Policy YAML file not found: {yaml_path}")

        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            logger.error(
                "PolicyEngine: PyYAML not installed. Install with: pip install pyyaml"
            )
            raise ImportError(
                "PyYAML is required to load policies from YAML. "
                "Install with: pip install pyyaml"
            )

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"YAML root must be a dict, got {type(data).__name__}")

        policies_data = data.get("policies", [])
        if not isinstance(policies_data, list):
            raise ValueError(
                f"'policies' key must be a list, got {type(policies_data).__name__}"
            )

        return self.load_policies_from_dict(policies_data)

    def load_policies_from_dict(self, policies: List[Dict[str, Any]]) -> int:
        """Load policy rules from a list of Python dicts.

        Each dict should have the same structure as the YAML format.

        Args:
            policies: List of policy dicts.

        Returns:
            Number of policies loaded.
        """
        with self._lock:
            loaded = 0
            for policy_data in policies:
                try:
                    rule = self._parse_policy_dict(policy_data)
                    self._policies[rule.name] = rule
                    loaded += 1
                    logger.info(
                        "PolicyEngine: Loaded policy '%s' (action=%s, priority=%d)",
                        rule.name, rule.action.value, rule.priority,
                    )
                except Exception as exc:
                    logger.warning(
                        "PolicyEngine: Failed to load policy from dict: %s — %s",
                        policy_data.get("name", "<unknown>"), exc,
                    )
            return loaded

    # ── Evaluation ────────────────────────────────────────

    def evaluate(
        self,
        action_type: str,
        config: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> PolicyDecision:
        """Evaluate all applicable policies for an action.

        Evaluation order:
          1. Sort policies by priority (higher = evaluated first).
          2. Evaluate each policy's condition.
          3. First DENY wins.
          4. First REQUIRE_APPROVAL / ESCALATE wins over ALLOW.
          5. Default: ALLOW.

        Args:
            action_type: The type of action being evaluated.
            config: The action configuration dict.
            context: Optional context dict (may contain category, user info, etc.).

        Returns:
            A PolicyDecision with the final determination.
        """
        with self._lock:
            self._eval_count += 1
            context = context or {}
            category = str(context.get("category", ""))

            # Sort policies by priority (descending)
            sorted_policies = sorted(
                self._policies.values(),
                key=lambda p: p.priority,
                reverse=True,
            )

            # Track results
            matched_rules: List[str] = []
            details: List[Dict[str, Any]] = []
            best_action: PolicyAction = PolicyAction.ALLOW
            denial_reason: str = ""
            escalation_role: str = ""

            for rule in sorted_policies:
                try:
                    if rule.matches(action_type, config, context, category):
                        matched_rules.append(rule.name)
                        detail: Dict[str, Any] = {
                            "rule_name": rule.name,
                            "action": rule.action.value,
                            "priority": rule.priority,
                        }
                        details.append(detail)

                        # Priority-based decision:
                        # DENY wins immediately
                        if rule.action == PolicyAction.DENY:
                            best_action = PolicyAction.DENY
                            denial_reason = (
                                f"Denied by policy '{rule.name}': {rule.description}"
                            )
                            break  # First DENY wins — stop evaluating

                        # REQUIRE_APPROVAL / ESCALATE / REQUIRE_CONFIRMATION
                        # win over ALLOW (but not over DENY)
                        if rule.action in (
                            PolicyAction.REQUIRE_APPROVAL,
                            PolicyAction.ESCALATE,
                            PolicyAction.REQUIRE_CONFIRMATION,
                        ):
                            if best_action == PolicyAction.ALLOW:
                                best_action = rule.action
                                if rule.action == PolicyAction.ESCALATE:
                                    escalation_role = rule.escalation_role

                except Exception as exc:
                    logger.warning(
                        "PolicyEngine: Error evaluating policy '%s': %s",
                        rule.name, exc,
                    )
                    details.append({
                        "rule_name": rule.name,
                        "error": str(exc),
                    })

            decision = PolicyDecision(
                action=best_action,
                action_type=action_type,
                matched_rules=matched_rules,
                denial_reason=denial_reason,
                escalation_role=escalation_role,
                requires_approval=(best_action == PolicyAction.REQUIRE_APPROVAL),
                requires_confirmation=(best_action == PolicyAction.REQUIRE_CONFIRMATION),
                evaluation_count=self._eval_count,
                details=details,
            )

            logger.info(
                "PolicyEngine: Evaluated '%s' → %s (matched: %s)",
                action_type, best_action.value,
                matched_rules if matched_rules else "none",
            )

            return decision

    # ── Policy Management ─────────────────────────────────

    def add_policy(self, policy: PolicyRule) -> None:
        """Add a single policy rule.

        If a policy with the same name already exists, it is replaced.

        Args:
            policy: The PolicyRule to add.
        """
        with self._lock:
            self._policies[policy.name] = policy
            logger.info(
                "PolicyEngine: Added policy '%s' (action=%s, priority=%d)",
                policy.name, policy.action.value, policy.priority,
            )

    def remove_policy(self, policy_name: str) -> bool:
        """Remove a policy by name.

        Args:
            policy_name: The name of the policy to remove.

        Returns:
            True if the policy was found and removed, False otherwise.
        """
        with self._lock:
            if policy_name in self._policies:
                del self._policies[policy_name]
                logger.info("PolicyEngine: Removed policy '%s'", policy_name)
                return True
            logger.warning("PolicyEngine: Policy '%s' not found for removal", policy_name)
            return False

    def list_policies(self) -> List[PolicyRule]:
        """List all loaded policies, sorted by priority (descending).

        Returns:
            List of all PolicyRule objects.
        """
        with self._lock:
            return sorted(
                list(self._policies.values()),
                key=lambda p: p.priority,
                reverse=True,
            )

    def get_applicable_policies(
        self,
        action_type: str,
        category: str = "",
    ) -> List[PolicyRule]:
        """Filter policies by action type and/or category.

        Returns policies whose conditions would potentially match
        the given action type, without full evaluation.

        Args:
            action_type: The action type to filter by.
            category: Optional category to filter by.

        Returns:
            List of applicable PolicyRule objects, sorted by priority (descending).
        """
        with self._lock:
            applicable: List[PolicyRule] = []
            for rule in self._policies.values():
                # Category filter
                if rule.category_filter and category:
                    if rule.category_filter.lower() != category.lower():
                        continue
                # Basic action_type check: if condition references action_type
                if rule.condition and rule.condition.field == "action_type":
                    # Check if the operator would match this action_type
                    # We do a lightweight check — full evaluation happens in evaluate()
                    if rule.condition.operator == ConditionOperator.EQ:
                        if rule.condition.value != action_type:
                            continue
                    elif rule.condition.operator == ConditionOperator.IN:
                        if isinstance(rule.condition.value, (list, tuple)):
                            if action_type not in rule.condition.value:
                                continue
                    elif rule.condition.operator == ConditionOperator.REGEX:
                        try:
                            if not re.search(str(rule.condition.value), action_type):
                                continue
                        except re.error:
                            pass
                    elif rule.condition.operator == ConditionOperator.CONTAINS:
                        if isinstance(rule.condition.value, str):
                            if rule.condition.value not in action_type:
                                continue
                applicable.append(rule)

            return sorted(applicable, key=lambda p: p.priority, reverse=True)

    # ── Stats ──────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        with self._lock:
            return {
                "policy_count": len(self._policies),
                "evaluation_count": self._eval_count,
                "policy_names": list(self._policies.keys()),
            }

    # ── Internal Parsing ──────────────────────────────────

    @staticmethod
    def _parse_policy_dict(data: Dict[str, Any]) -> PolicyRule:
        """Parse a policy dict into a PolicyRule.

        Expected keys:
          - name (required)
          - description
          - condition: {field, operator, value}
          - action: ALLOW | DENY | REQUIRE_APPROVAL | REQUIRE_CONFIRMATION | ESCALATE
          - priority
          - escalation_role
          - category_filter
        """
        name = data.get("name")
        if not name or not isinstance(name, str):
            raise ValueError(f"Policy must have a non-empty string 'name', got: {name!r}")

        # Parse condition
        condition: Optional[PolicyCondition] = None
        cond_data = data.get("condition")
        if cond_data and isinstance(cond_data, dict):
            cond_field = cond_data.get("field", "")
            cond_op_str = cond_data.get("operator", "eq")
            cond_value = cond_data.get("value")

            if not cond_field:
                raise ValueError(
                    f"Policy '{name}': condition must have a 'field'"
                )

            try:
                cond_op = ConditionOperator(cond_op_str)
            except ValueError:
                raise ValueError(
                    f"Policy '{name}': invalid operator '{cond_op_str}'. "
                    f"Must be one of: {[o.value for o in ConditionOperator]}"
                )

            condition = PolicyCondition(
                field=cond_field,
                operator=cond_op,
                value=cond_value,
            )

        # Parse action
        action_str = data.get("action", "ALLOW")
        try:
            action = PolicyAction(action_str)
        except ValueError:
            raise ValueError(
                f"Policy '{name}': invalid action '{action_str}'. "
                f"Must be one of: {[a.value for a in PolicyAction]}"
            )

        return PolicyRule(
            name=name,
            description=str(data.get("description", "")),
            condition=condition,
            action=action,
            priority=int(data.get("priority", 0)),
            escalation_role=str(data.get("escalation_role", "")),
            category_filter=str(data.get("category_filter", "")),
        )


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

_policy_engine: Optional[PolicyEngine] = None
_policy_engine_lock = threading.Lock()


def get_policy_engine() -> PolicyEngine:
    """Get or create the global PolicyEngine instance."""
    global _policy_engine
    with _policy_engine_lock:
        if _policy_engine is None:
            _policy_engine = PolicyEngine()
        return _policy_engine


def reset_policy_engine() -> None:
    """Reset the global PolicyEngine (for testing)."""
    global _policy_engine
    with _policy_engine_lock:
        _policy_engine = None


__all__ = [
    # Enums
    "PolicyAction",
    "ConditionOperator",
    # Dataclasses
    "PolicyCondition",
    "PolicyRule",
    "PolicyDecision",
    # Engine
    "PolicyEngine",
    # Singleton
    "get_policy_engine",
    "reset_policy_engine",
]
