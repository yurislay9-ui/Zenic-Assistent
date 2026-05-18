"""Core logic for conditional_branch."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

from .chain_composer import ChainStep
from ._types import *
from ._helpers import *


logger = logging.getLogger(__name__)


class ConditionalBranching:
    """Manages conditional branching logic within workflow chains.

    Provides expression evaluation, branch selection, and rule CRUD.
    In-memory storage (rules are small and loaded from templates).
    Thread-safe via RLock.  Singleton via get_conditional_branching().
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rules: dict[str, BranchRule] = {}
        logger.info("ConditionalBranching initialized")

    # ------------------------------------------------------------------
    #  Evaluation
    # ------------------------------------------------------------------

    @staticmethod
    def evaluate(condition: str, context: dict[str, Any]) -> bool:
        """Evaluate a condition expression against context data.

        Uses the safe custom parser — no exec/eval.
        """
        return safe_evaluate(condition, context)

    def select_branch(self, step: ChainStep, context: dict[str, Any]) -> str | None:
        """Given a step with branches, return the next_step_id of the matching branch.

        Resolution order:
          1. If the step has a condition_expr, evaluate it:
             - If True, return step.next_step_id
             - If False, look for matching branch rules
          2. Check registered BranchRules for matching conditions
          3. Return the step's next_step_id as default, or None

        Args:
            step: The ChainStep to evaluate branching for.
            context: The current execution context.

        Returns:
            The step_id of the next step to execute, or None.
        """
        with self._lock:
            # 1. Evaluate the step's own condition_expr
            if step.condition_expr:
                result = safe_evaluate(step.condition_expr, context)
                if result:
                    return step.next_step_id
                # Condition failed — look for branch rules
            else:
                # No condition — if there's a next_step_id, follow it
                if step.next_step_id:
                    return step.next_step_id

            # 2. Check registered branch rules
            matching_rules = sorted(
                [r for r in self._rules.values()],
                key=lambda r: r.priority,
                reverse=True,
            )

            for rule in matching_rules:
                for condition in rule.conditions:
                    if safe_evaluate(condition.expression, context):
                        logger.debug(
                            "Branch rule '%s' matched condition '%s' → %s",
                            rule.name, condition.description or condition.expression,
                            condition.target_step_id,
                        )
                        return condition.target_step_id
                # No condition matched — use rule default if applicable
                if rule.default_branch:
                    return rule.default_branch

            # 3. Fallback
            return step.next_step_id or None

    # ------------------------------------------------------------------
    #  Rule CRUD
    # ------------------------------------------------------------------

    def register_branch_rule(self, rule: BranchRule) -> str:
        """Register a branch rule. Returns the rule_id.

        If rule.rule_id is empty, a UUID is generated.
        """
        with self._lock:
            if not rule.rule_id:
                rule.rule_id = f"br_{uuid.uuid4().hex[:12]}"
            if not rule.created_at:
                rule.created_at = time.time()
            self._rules[rule.rule_id] = rule
            logger.info(
                "Registered branch rule %s: %s (%d conditions)",
                rule.rule_id, rule.name, len(rule.conditions),
            )
            return rule.rule_id

    def unregister_branch_rule(self, rule_id: str) -> bool:
        """Remove a branch rule by ID. Returns True if found and removed."""
        with self._lock:
            if rule_id not in self._rules:
                logger.warning("Branch rule %s not found for removal", rule_id)
                return False
            del self._rules[rule_id]
            logger.info("Unregistered branch rule %s", rule_id)
            return True

    def list_branch_rules(self) -> list[BranchRule]:
        """List all registered branch rules."""
        with self._lock:
            return sorted(
                list(self._rules.values()),
                key=lambda r: (r.priority, r.name),
                reverse=True,
            )


# ---------------------------------------------------------------------------
#  Singleton
# ---------------------------------------------------------------------------
