"""
ZENIC-AGENTS — InterWorkflowHandoff: passes output between chains.

When a source chain completes, handoff rules determine whether and how
its output should be forwarded as input to a target chain.  Supports:

  - Field mapping (dot-notation source → target paths)
  - Condition evaluation (safe expression check before handoff)
  - Retry on target chain execution (3 retries, 1 s backoff)

Thread-safe via RLock. Persisted to SQLite (inter_workflow.sqlite).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Persistence paths
# ---------------------------------------------------------------------------

_DB_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "db")
_DB_PATH = os.path.join(_DB_DIR, "inter_workflow.sqlite")

# ---------------------------------------------------------------------------
#  Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FieldMapping:
    """A single source→target field mapping specification."""

    source_path: str = ""  # e.g. "output.invoice_id"
    target_path: str = ""  # e.g. "input.invoice_id"


@dataclass
class HandoffRule:
    """A rule that wires a source chain's output to a target chain's input."""

    handoff_id: str = ""
    source_chain_id: str = ""
    target_chain_id: str = ""
    field_mapping: dict[str, str] = field(default_factory=dict)
    condition: str = ""
    enabled: bool = True
    created_at: float = 0.0


@dataclass
class HandoffResult:
    """Result of executing a single handoff."""

    handoff_id: str = ""
    success: bool = False
    target_chain_id: str = ""
    mapped_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


# ---------------------------------------------------------------------------
#  Safe expression evaluation
# ---------------------------------------------------------------------------

_ALLOWED_NAMES: set[str] = {
    "True", "False", "None",
    "and", "or", "not",
    "abs", "len", "min", "max", "sum",
    "int", "float", "str", "bool",
}

_COMPARISON_OPS = re.compile(
    r"^\s*([a-zA-Z_][\w.]*)\s*(==|!=|>=|<=|>|<)\s*(.+?)\s*$"
)


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

    from .conditional_branch import safe_evaluate
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


# Keywords that should NOT be prefixed with "context."
_KEYWORDS = frozenset({
    "and", "or", "not", "True", "False", "None",
    "contains", "startswith", "endswith", "exists", "not_empty",
})


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


# ---------------------------------------------------------------------------
#  InterWorkflowHandoff
# ---------------------------------------------------------------------------


class InterWorkflowHandoff:
    """Manages handoff rules and execution between workflow chains.

    Thread-safe via RLock. Persisted to SQLite. Singleton via
    get_inter_workflow_handoff().
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rules: dict[str, HandoffRule] = {}
        os.makedirs(_DB_DIR, exist_ok=True)
        self._init_db()
        self._load_rules()
        logger.info("InterWorkflowHandoff initialized with %d rules", len(self._rules))

    # ------------------------------------------------------------------
    #  Database
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS handoff_rules (
                    handoff_id       TEXT PRIMARY KEY,
                    source_chain_id  TEXT NOT NULL,
                    target_chain_id  TEXT NOT NULL,
                    field_mapping    TEXT NOT NULL DEFAULT '{}',
                    condition        TEXT NOT NULL DEFAULT '',
                    enabled          INTEGER NOT NULL DEFAULT 1,
                    created_at       REAL NOT NULL DEFAULT 0.0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS handoff_execution_log (
                    log_id           TEXT PRIMARY KEY,
                    handoff_id       TEXT NOT NULL,
                    source_chain_id  TEXT NOT NULL,
                    target_chain_id  TEXT NOT NULL,
                    success          INTEGER NOT NULL DEFAULT 0,
                    mapped_data      TEXT NOT NULL DEFAULT '{}',
                    error            TEXT,
                    executed_at      REAL NOT NULL DEFAULT 0.0
                )
                """
            )
            conn.commit()

    def _load_rules(self) -> None:
        with sqlite3.connect(_DB_PATH) as conn:
            rows = conn.execute(
                "SELECT handoff_id, source_chain_id, target_chain_id, "
                "field_mapping, condition, enabled, created_at "
                "FROM handoff_rules"
            ).fetchall()

        for row in rows:
            handoff_id = row[0]
            try:
                rule = HandoffRule(
                    handoff_id=handoff_id,
                    source_chain_id=row[1],
                    target_chain_id=row[2],
                    field_mapping=json.loads(row[3]) if row[3] else {},
                    condition=row[4] or "",
                    enabled=bool(row[5]),
                    created_at=row[6],
                )
                self._rules[handoff_id] = rule
            except (json.JSONDecodeError, TypeError, KeyError) as exc:
                logger.warning("Failed to load handoff rule %s: %s", handoff_id, exc)

    def _save_rule(self, rule: HandoffRule) -> None:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO handoff_rules
                    (handoff_id, source_chain_id, target_chain_id,
                     field_mapping, condition, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule.handoff_id,
                    rule.source_chain_id,
                    rule.target_chain_id,
                    json.dumps(rule.field_mapping),
                    rule.condition,
                    1 if rule.enabled else 0,
                    rule.created_at,
                ),
            )
            conn.commit()

    def _log_handoff(self, result: HandoffResult, source_chain_id: str) -> None:
        log_id = f"hlog_{uuid.uuid4().hex[:12]}"
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO handoff_execution_log
                    (log_id, handoff_id, source_chain_id, target_chain_id,
                     success, mapped_data, error, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    result.handoff_id,
                    source_chain_id,
                    result.target_chain_id,
                    1 if result.success else 0,
                    json.dumps(result.mapped_data, default=str),
                    result.error,
                    time.time(),
                ),
            )
            conn.commit()

    # ------------------------------------------------------------------
    #  CRUD
    # ------------------------------------------------------------------

    def register_handoff(
        self,
        source_chain_id: str,
        target_chain_id: str,
        field_mapping: dict[str, str],
        condition: str | None = None,
    ) -> str:
        """Register a handoff rule. Returns the handoff_id."""
        with self._lock:
            handoff_id = f"hoff_{uuid.uuid4().hex[:12]}"
            rule = HandoffRule(
                handoff_id=handoff_id,
                source_chain_id=source_chain_id,
                target_chain_id=target_chain_id,
                field_mapping=field_mapping,
                condition=condition or "",
                enabled=True,
                created_at=time.time(),
            )
            self._rules[handoff_id] = rule
            self._save_rule(rule)
            logger.info(
                "Registered handoff %s: %s → %s",
                handoff_id, source_chain_id, target_chain_id,
            )
            return handoff_id

    def unregister_handoff(self, handoff_id: str) -> bool:
        """Remove a handoff rule. Returns True if found and removed."""
        with self._lock:
            if handoff_id not in self._rules:
                logger.warning("Handoff %s not found for removal", handoff_id)
                return False
            del self._rules[handoff_id]
            with sqlite3.connect(_DB_PATH) as conn:
                conn.execute("DELETE FROM handoff_rules WHERE handoff_id=?", (handoff_id,))
                conn.commit()
            logger.info("Unregistered handoff %s", handoff_id)
            return True

    def list_handoffs(self, source_chain_id: str | None = None) -> list[HandoffRule]:
        """List handoff rules, optionally filtered by source chain."""
        with self._lock:
            rules = list(self._rules.values())
        if source_chain_id is not None:
            rules = [r for r in rules if r.source_chain_id == source_chain_id]
        return sorted(rules, key=lambda r: r.created_at)

    # ------------------------------------------------------------------
    #  Execution
    # ------------------------------------------------------------------

    def execute_handoff(
        self,
        source_chain_id: str,
        source_output: dict[str, Any],
        tenant_id: str,
    ) -> list[HandoffResult]:
        """Execute all matching handoffs for a completed source chain.

        For each enabled rule whose source_chain_id matches and whose
        condition (if any) evaluates to True:
          1. Map fields from source_output using the rule's field_mapping
          2. Trigger the target chain with the mapped data
          3. Retry on failure (3 attempts, 1 s backoff)

        Returns a list of HandoffResult, one per executed rule.
        """
        results: list[HandoffResult] = []

        with self._lock:
            matching_rules = [
                r for r in self._rules.values()
                if r.source_chain_id == source_chain_id and r.enabled
            ]

        if not matching_rules:
            logger.debug("No enabled handoff rules for source chain %s", source_chain_id)
            return results

        for rule in matching_rules:
            # Evaluate condition
            if rule.condition and not _safe_eval_condition(rule.condition, source_output):
                logger.debug(
                    "Handoff %s condition not met: %s", rule.handoff_id, rule.condition,
                )
                continue

            # Map fields
            mapped_data: dict[str, Any] = {}
            mapping_errors: list[str] = []

            for source_path, target_path in rule.field_mapping.items():
                value = _resolve_dot_path(source_output, source_path)
                if value is not None:
                    # Set value at target_path (support nested dot paths)
                    _set_dot_path(mapped_data, target_path, value)
                else:
                    mapping_errors.append(f"Source path '{source_path}' not found")

            if mapping_errors:
                logger.warning(
                    "Handoff %s mapping issues: %s", rule.handoff_id, "; ".join(mapping_errors),
                )

            # Execute target chain with retry
            result = self._execute_target_with_retry(
                rule=rule,
                mapped_data=mapped_data,
                tenant_id=tenant_id,
            )
            results.append(result)
            self._log_handoff(result, source_chain_id)

        return results

    def _execute_target_with_retry(
        self,
        rule: HandoffRule,
        mapped_data: dict[str, Any],
        tenant_id: str,
    ) -> HandoffResult:
        """Try to execute the target chain, retrying up to 3 times with 1 s backoff."""
        max_retries = 3
        base_delay = 1.0  # 1 second

        for attempt in range(1, max_retries + 1):
            try:
                # Try to compose and execute via the chain composer
                from .chain_composer import get_chain_composer

                composer = get_chain_composer()
                target_chain = composer.get_chain(rule.target_chain_id)

                if target_chain is not None:
                    # Inject mapped data into the chain's first step config
                    if target_chain.steps:
                        target_chain.steps[0].config.update(mapped_data)

                    exec_result = composer.execute_chain(target_chain)
                    if exec_result.success:
                        return HandoffResult(
                            handoff_id=rule.handoff_id,
                            success=True,
                            target_chain_id=rule.target_chain_id,
                            mapped_data=mapped_data,
                            error=None,
                        )
                    else:
                        last_error = exec_result.error or "Target chain execution failed"
                else:
                    # Chain not found in composer — try to instantiate from template
                    try:
                        template_chain = composer.template_library.instantiate(
                            rule.target_chain_id, mapped_data,
                        )
                        template_chain.tenant_id = tenant_id
                        exec_result = composer.execute_chain(template_chain)
                        if exec_result.success:
                            return HandoffResult(
                                handoff_id=rule.handoff_id,
                                success=True,
                                target_chain_id=rule.target_chain_id,
                                mapped_data=mapped_data,
                                error=None,
                            )
                        last_error = exec_result.error or "Target chain execution failed"
                    except (KeyError, ValueError) as exc:
                        last_error = f"Target template not found: {exc}"

            except Exception as exc:
                last_error = str(exc)

            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                logger.debug(
                    "Handoff %s target execution failed (attempt %d/%d): %s — retrying in %.1fs",
                    rule.handoff_id, attempt, max_retries, last_error, delay,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "Handoff %s to %s failed after %d attempts: %s",
                    rule.handoff_id, rule.target_chain_id, max_retries, last_error,
                )

        return HandoffResult(
            handoff_id=rule.handoff_id,
            success=False,
            target_chain_id=rule.target_chain_id,
            mapped_data=mapped_data,
            error=last_error,
        )


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
#  Singleton
# ---------------------------------------------------------------------------

_instance: InterWorkflowHandoff | None = None
_instance_lock = threading.Lock()


def get_inter_workflow_handoff() -> InterWorkflowHandoff:
    """Return the InterWorkflowHandoff singleton (thread-safe)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = InterWorkflowHandoff()
    return _instance


__all__ = [
    "HandoffRule",
    "HandoffResult",
    "FieldMapping",
    "InterWorkflowHandoff",
    "get_inter_workflow_handoff",
]
