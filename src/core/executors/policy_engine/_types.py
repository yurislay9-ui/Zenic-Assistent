"""
ZENIC-AGENTS — Policy Engine Types

Enums and dataclasses used by the policy engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


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
    condition: Optional[Any] = None  # PolicyCondition — avoids circular import
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
