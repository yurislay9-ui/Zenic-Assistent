"""Helpers for conditional_branch."""

from __future__ import annotations

import logging
import re
from typing import Any

from .chain_composer import ChainStep
from ._types import _TOKEN_RE, _KEYWORDS

logger = logging.getLogger(__name__)


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
