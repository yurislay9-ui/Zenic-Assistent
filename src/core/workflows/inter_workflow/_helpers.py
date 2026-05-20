"""Helpers for inter_workflow."""

from __future__ import annotations
import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from typing import Any

from ._types import _KEYWORDS

logger = logging.getLogger(__name__)

def _resolve_dot_path(data: dict[str, Any], path: str) -> Any:
    """Resolve a dot-notation path like 'output.invoice_id' from a dict.

    Traverses nested dicts.  Returns None if any segment is missing.
    """
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current



def _safe_eval_condition(condition: str, source_output: dict[str, Any]) -> bool:
    """Evaluate a simple condition expression against source output data.

    Delegates to the full-featured safe_evaluate from conditional_branch,
    wrapping source_output so that dot-paths like "output.amount" resolve
    correctly.  If source_output has a top-level key matching the first
    path segment (e.g. "output"), the nested value is used; otherwise
    the path is tried directly against the flat dict.

    Supports expressions like:
      - "output.amount > 10000"
      - "output.status == 'active'"
      - "output.count >= 3 or output.severity == 'critical'"
    """
    if not condition or not condition.strip():
        return True

    # Build a context that the conditional_branch evaluator can use.
    # The evaluator resolves "context.X" to context[X], so we provide
    # the source_output under a "context" wrapper that also supports
    # direct dot-path access.
    eval_context = _build_eval_context(source_output)

    from ..conditional_branch import safe_evaluate
    # Prefix identifiers with "context." so the evaluator can resolve them
    # using its own dot-notation resolution.
    rewritten = _prefix_context(condition)
    return safe_evaluate(rewritten, eval_context)



def _build_eval_context(source_output: dict[str, Any]) -> dict[str, Any]:
    """Build an evaluation context from source_output.

    Ensures that both flat dicts like {"amount": 50000} and nested
    dicts like {"output": {"amount": 50000}} can be resolved via
    "context.amount" and "context.output.amount" respectively.
    """
    # Merge the flat keys directly into the context root so that
    # "context.amount" works for {"amount": 50000}.
    context: dict[str, Any] = dict(source_output)
    # Also ensure nested sub-dicts are preserved for dot access.
    return context



def _prefix_context(expression: str) -> str:
    """Prefix bare identifiers with 'context.' for the evaluator.

    Transforms e.g. "output.amount > 10000" into
    "context.output.amount > 10000" so that the evaluator's
    _resolve_context_path can find the values.  Skips string
    literals and keywords.
    """
    # Tokenize into string-literal and non-literal segments, then
    # only replace identifiers in the non-literal parts.
    parts: list[str] = []
    i = 0
    while i < len(expression):
        ch = expression[i]
        if ch in ("'", '"'):
            # Find the matching close quote
            close = expression.find(ch, i + 1)
            if close == -1:
                # No close quote — take the rest as a literal
                parts.append(expression[i:])
                break
            parts.append(expression[i:close + 1])
            i = close + 1
        else:
            # Collect characters until the next quote
            next_quote = len(expression)
            for q in ("'", '"'):
                pos = expression.find(q, i)
                if pos != -1 and pos < next_quote:
                    next_quote = pos
            segment = expression[i:next_quote]
            parts.append(_replace_identifiers(segment))
            i = next_quote

    return "".join(parts)



def _replace_identifiers(segment: str) -> str:
    """Replace bare identifiers in a non-literal segment with context.-prefixed ones."""
    def _replace(match: re.Match[str]) -> str:
        ident = match.group(0)
        if ident in _KEYWORDS:
            return ident
        if ident.startswith("context."):
            return ident
        return f"context.{ident}"

    return re.sub(r'[a-zA-Z_][\w.]*', _replace, segment)



def _set_dot_path(data: dict[str, Any], path: str, value: Any) -> None:
    """Set a value at a dot-notation path in a nested dict.

    Creates intermediate dicts as needed.
    """
    parts = path.split(".")
    current = data
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


