"""
ZENIC-AGENTS — ConditionalBranching: if/then/else logic within chains.

Evaluates condition expressions against context data to determine
which branch (next_step_id) a chain should follow.  Uses a custom
safe parser — no exec/eval — supporting:

  - Comparisons: ==, !=, >, <, >=, <=
  - Logical operators: and, or, not
  - String operations: contains, startswith, endswith
  - Existence checks: exists, not_empty
  - Dot-notation context access: context.stock_level, context.amount

Thread-safe via RLock. In-memory storage (rules are small and loaded
from templates).  Singleton via get_conditional_branching().
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .chain_composer import ChainStep

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class BranchCondition:
    """A single condition that maps to a target step."""

    expression: str = ""
    target_step_id: str = ""
    description: str = ""


@dataclass
class BranchRule:
    """A named collection of branch conditions with a default branch."""

    rule_id: str = ""
    name: str = ""
    conditions: list[BranchCondition] = field(default_factory=list)
    default_branch: str = ""
    priority: int = 0
    created_at: float = 0.0


# ---------------------------------------------------------------------------
#  Safe expression parser
# ---------------------------------------------------------------------------

# Token patterns
_TOKEN_RE = re.compile(
    r"""
    (?P<STRING>   '(?:[^'\\]|\\.)*' | "(?:[^"\\]|\\.)*" )  |
    (?P<NUMBER>   -?\d+\.\d+ | -?\d+)                      |
    (?P<BOOL>     True | False | None)                      |
    (?P<KEYWORD>  and|or|not|contains|startswith|endswith|exists|not_empty) |
    (?P<OP>       ==|!=|>=|<=|>|<)                          |
    (?P<IDENT>    [a-zA-Z_][\w.]*)                          |
    (?P<LPAREN>   \()                                       |
    (?P<RPAREN>   \))                                       |
    (?P<COMMA>    ,)                                        |
    (?P<WS>       \s+)                                      |
    (?P<MISMATCH> .)
    """,
    re.VERBOSE,
)


def _tokenize(expression: str) -> list[tuple[str, str]]:
    """Tokenize an expression string into (token_type, value) pairs."""
    tokens: list[tuple[str, str]] = []
    for m in _TOKEN_RE.finditer(expression):
        kind = m.lastgroup
        value = m.group()
        if kind == "WS":
            continue
        if kind == "MISMATCH":
            raise SyntaxError(f"Unexpected character at position {m.start()}: {value!r}")
        tokens.append((kind, value))
    return tokens


def _resolve_context_path(context: dict[str, Any], path: str) -> Any:
    """Resolve a dot-notation path from context dict.

    Supports 'context.field' as well as bare 'field' (auto-prefixed
    with 'context.').
    """
    if path.startswith("context."):
        path = path[8:]  # strip 'context.' prefix

    parts = path.split(".")
    current: Any = context
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _parse_value(raw: str) -> Any:
    """Parse a raw token value into a Python object."""
    if (raw.startswith("'") and raw.endswith("'")) or \
       (raw.startswith('"') and raw.endswith('"')):
        return raw[1:-1]
    if raw == "True":
        return True
    if raw == "False":
        return False
    if raw == "None":
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


class _ExpressionEvaluator:
    """Recursive-descent evaluator for safe condition expressions.

    Grammar (simplified):
        expr     ::= or_expr
        or_expr  ::= and_expr ('or' and_expr)*
        and_expr ::= not_expr ('and' not_expr)*
        not_expr ::= 'not' not_expr | comparison
        comparison ::= value (op value)?
                   | value 'contains' value
                   | value 'startswith' value
                   | value 'endswith' value
                   | value 'exists'
                   | value 'not_empty'
        value    ::= STRING | NUMBER | BOOL | IDENT | '(' expr ')'
    """

    def __init__(self, tokens: list[tuple[str, str]], context: dict[str, Any]) -> None:
        self._tokens = tokens
        self._pos = 0
        self._context = context

    def evaluate(self) -> bool:
        if not self._tokens:
            return True
        result = self._parse_or_expr()
        return bool(result)

    def _peek(self) -> tuple[str, str] | None:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _consume(self, expected_kind: str | None = None) -> tuple[str, str]:
        if self._pos >= len(self._tokens):
            raise SyntaxError("Unexpected end of expression")
        kind, value = self._tokens[self._pos]
        if expected_kind and kind != expected_kind:
            raise SyntaxError(f"Expected {expected_kind}, got {kind} ({value!r})")
        self._pos += 1
        return kind, value

    # ---- Recursive descent rules ----

    def _parse_or_expr(self) -> Any:
        left = self._parse_and_expr()
        while self._peek() and self._peek()[0] == "KEYWORD" and self._peek()[1] == "or":
            self._consume()
            right = self._parse_and_expr()
            left = bool(left) or bool(right)
        return left

    def _parse_and_expr(self) -> Any:
        left = self._parse_not_expr()
        while self._peek() and self._peek()[0] == "KEYWORD" and self._peek()[1] == "and":
            self._consume()
            right = self._parse_not_expr()
            left = bool(left) and bool(right)
        return left

    def _parse_not_expr(self) -> Any:
        if self._peek() and self._peek()[0] == "KEYWORD" and self._peek()[1] == "not":
            self._consume()
            operand = self._parse_not_expr()
            return not bool(operand)
        return self._parse_comparison()

    def _parse_comparison(self) -> Any:
        left = self._parse_value()

        peek = self._peek()
        if peek is None:
            return left

        # Check for comparison operator
        if peek[0] == "OP":
            op_kind, op_val = self._consume()
            right = self._parse_value()
            return self._apply_comparison(left, op_val, right)

        # Check for keyword operators
        if peek[0] == "KEYWORD" and peek[1] in ("contains", "startswith", "endswith"):
            _, op_name = self._consume()
            right = self._parse_value()
            return self._apply_string_op(left, op_name, right)

        if peek[0] == "KEYWORD" and peek[1] == "exists":
            self._consume()
            return left is not None

        if peek[0] == "KEYWORD" and peek[1] == "not_empty":
            self._consume()
            return left is not None and left != "" and left != 0 and left != [] and left != {}

        return left

    def _parse_value(self) -> Any:
        peek = self._peek()
        if peek is None:
            raise SyntaxError("Unexpected end of expression — expected a value")

        kind, value = peek

        if kind == "STRING":
            self._consume()
            return value[1:-1]

        if kind == "NUMBER":
            self._consume()
            if "." in value:
                return float(value)
            return int(value)

        if kind == "BOOL":
            self._consume()
            if value == "True":
                return True
            if value == "False":
                return False
            return None

        if kind == "IDENT":
            self._consume()
            resolved = _resolve_context_path(self._context, value)
            if resolved is not None:
                return resolved
            # Try as-is (bare name might be a variable not in context)
            return _resolve_context_path(self._context, f"context.{value}")

        if kind == "LPAREN":
            self._consume()
            inner = self._parse_or_expr()
            if self._peek() and self._peek()[0] == "RPAREN":
                self._consume()
            return inner

        raise SyntaxError(f"Unexpected token: {kind} ({value!r})")

    @staticmethod
    def _apply_comparison(left: Any, op: str, right: Any) -> bool:
        try:
            if op == "==":
                return left == right
            if op == "!=":
                return left != right
            if op == ">":
                return left > right  # type: ignore[operator]
            if op == "<":
                return left < right  # type: ignore[operator]
            if op == ">=":
                return left >= right  # type: ignore[operator]
            if op == "<=":
                return left <= right  # type: ignore[operator]
        except TypeError:
            return False
        return False

    @staticmethod
    def _apply_string_op(left: Any, op: str, right: Any) -> bool:
        left_str = str(left) if left is not None else ""
        right_str = str(right) if right is not None else ""
        if op == "contains":
            return right_str in left_str
        if op == "startswith":
            return left_str.startswith(right_str)
        if op == "endswith":
            return left_str.endswith(right_str)
        return False


def safe_evaluate(expression: str, context: dict[str, Any]) -> bool:
    """Safely evaluate a condition expression against context data.

    No exec/eval — uses a custom recursive-descent parser.

    Examples:
        >>> safe_evaluate("context.stock_level < 10", {"stock_level": 5})
        True
        >>> safe_evaluate("context.amount > 10000 and context.category == 'financial'", {"amount": 15000, "category": "financial"})
        True
        >>> safe_evaluate("context.error_count >= 3 or context.severity == 'critical'", {"error_count": 2, "severity": "critical"})
        True
    """
    if not expression or not expression.strip():
        return True

    try:
        tokens = _tokenize(expression.strip())
        evaluator = _ExpressionEvaluator(tokens, context)
        return evaluator.evaluate()
    except (SyntaxError, IndexError, ValueError) as exc:
        logger.warning("Failed to evaluate expression '%s': %s — defaulting to False", expression, exc)
        return False


# ---------------------------------------------------------------------------
#  ConditionalBranching
# ---------------------------------------------------------------------------


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

_instance: ConditionalBranching | None = None
_instance_lock = threading.Lock()


def get_conditional_branching() -> ConditionalBranching:
    """Return the ConditionalBranching singleton (thread-safe)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ConditionalBranching()
    return _instance


__all__ = [
    "BranchRule",
    "BranchCondition",
    "ConditionalBranching",
    "get_conditional_branching",
]
