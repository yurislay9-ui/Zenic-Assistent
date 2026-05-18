"""
ZENIC-AGENTS — Policy-as-Code Engine (A2: Pre-action Validation Enhancement)

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
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._evaluator import PolicyCondition
from ._types import ConditionOperator, PolicyAction, PolicyDecision, PolicyRule

logger = logging.getLogger(__name__)


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
