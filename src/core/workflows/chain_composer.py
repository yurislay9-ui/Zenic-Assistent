"""
ZENIC-AGENTS — DynamicChainComposer: composes & executes workflow chains.

Dynamically selects chain templates from events or natural-language
intents, instantiates them, validates, and executes step by step with
retry logic and exponential backoff.

Thread-safe via RLock. Persisted to SQLite (chain_composer.sqlite).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Persistence paths
# ---------------------------------------------------------------------------

_DB_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "db")
_DB_PATH = os.path.join(_DB_DIR, "chain_composer.sqlite")

# ---------------------------------------------------------------------------
#  Enums
# ---------------------------------------------------------------------------


class ChainStepType(str, Enum):
    """Types of steps in a composed chain."""

    TRIGGER = "trigger"
    CONDITION = "condition"
    ACTION = "action"
    NOTIFICATION = "notification"
    DELAY = "delay"
    SUB_CHAIN = "sub_chain"


class ChainStatus(str, Enum):
    """Lifecycle status of a composed chain."""

    DRAFT = "draft"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
#  Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ChainStep:
    """A single executable step within a composed chain."""

    step_id: str = ""
    step_type: ChainStepType = ChainStepType.ACTION
    config: dict[str, Any] = field(default_factory=dict)
    next_step_id: str = ""
    condition_expr: str = ""
    timeout_ms: int = 30000
    retry_count: int = 3


@dataclass
class ComposedChain:
    """An instantiated, executable workflow chain."""

    chain_id: str = ""
    name: str = ""
    description: str = ""
    steps: list[ChainStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    tenant_id: str = ""
    created_at: float = 0.0
    status: ChainStatus = ChainStatus.DRAFT


@dataclass
class ChainStepResult:
    """Result of executing a single chain step."""

    step_id: str = ""
    success: bool = False
    output: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    retry_count: int = 0
    error: str | None = None


@dataclass
class ChainExecutionResult:
    """Result of executing an entire chain."""

    chain_id: str = ""
    success: bool = False
    step_results: list[ChainStepResult] = field(default_factory=list)
    total_duration_ms: int = 0
    failed_step: str | None = None
    error: str | None = None


@dataclass
class ChainValidationResult:
    """Validation outcome for a composed chain."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
#  Step executor helpers
# ---------------------------------------------------------------------------


def _execute_trigger_step(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Execute a trigger step: capture event data into context."""
    event_type = config.get("event_type", "unknown")
    return {
        "triggered": True,
        "event_type": event_type,
        "source": config.get("source", "unknown"),
        **{k: v for k, v in config.items() if k not in ("event_type", "source")},
    }


def _execute_condition_step(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Execute a condition/validation step."""
    check_type = config.get("check_type", "generic")
    # In production this would delegate to real validators.
    # Here we report pass/fail based on context availability.
    passed = bool(context)
    return {
        "check_type": check_type,
        "passed": passed,
        "details": f"Condition check '{check_type}' {'passed' if passed else 'failed'}",
    }


def _execute_action_step(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Execute an action step (create_task, create_reorder, database_operation, etc.)."""
    action_type = config.get("action_type", "generic")
    return {
        "action_type": action_type,
        "executed": True,
        "target": config.get("target_table", config.get("product_id", config.get("invoice_id", ""))),
        **{k: v for k, v in config.items() if k != "action_type"},
    }


def _execute_notification_step(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Execute a notification step."""
    channel = config.get("channel", "email")
    recipient = config.get("recipient", "unknown")
    message_template = config.get("message_template", "")
    # Simple template substitution from context
    message = message_template
    for key, value in context.items():
        if isinstance(value, (str, int, float)):
            message = message.replace("{{" + key + "}}", str(value))
    return {
        "channel": channel,
        "recipient": recipient,
        "message": message,
        "sent": True,
    }


def _execute_delay_step(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Execute a delay step (non-blocking in real impl; here we just record it)."""
    delay_ms = config.get("delay_ms", 1000)
    return {
        "delay_ms": delay_ms,
        "waited": True,
    }


def _execute_sub_chain_step(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Execute a sub-chain step (would recursively execute another chain)."""
    sub_chain_id = config.get("sub_chain_id", "")
    return {
        "sub_chain_id": sub_chain_id,
        "executed": True,
        "note": "Sub-chain execution is recorded; actual recursion handled by orchestrator",
    }


_STEP_EXECUTORS: dict[ChainStepType, Any] = {
    ChainStepType.TRIGGER: _execute_trigger_step,
    ChainStepType.CONDITION: _execute_condition_step,
    ChainStepType.ACTION: _execute_action_step,
    ChainStepType.NOTIFICATION: _execute_notification_step,
    ChainStepType.DELAY: _execute_delay_step,
    ChainStepType.SUB_CHAIN: _execute_sub_chain_step,
}


# ---------------------------------------------------------------------------
#  DynamicChainComposer
# ---------------------------------------------------------------------------


class DynamicChainComposer:
    """Composes workflow chains dynamically from events and templates.

    Thread-safe via RLock. Persisted to SQLite. Singleton via
    get_chain_composer().
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._chains: dict[str, ComposedChain] = {}
        os.makedirs(_DB_DIR, exist_ok=True)
        self._init_db()
        self._load_chains()

        # Lazy template library reference
        self._template_library: Any = None

        logger.info("DynamicChainComposer initialized with %d chains", len(self._chains))

    # ------------------------------------------------------------------
    #  Template library access (lazy)
    # ------------------------------------------------------------------

    @property
    def template_library(self) -> Any:
        """Lazy-load the ChainTemplateLibrary singleton."""
        if self._template_library is None:
            from .chain_templates import get_template_library
            self._template_library = get_template_library()
        return self._template_library

    # ------------------------------------------------------------------
    #  Database
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Create the chains table if it does not exist."""
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                CREATE TABLE IF NOT EXISTS composed_chains (
                    chain_id     TEXT PRIMARY KEY,
                    name         TEXT NOT NULL,
                    description  TEXT NOT NULL DEFAULT '',
                    steps        TEXT NOT NULL DEFAULT '[]',
                    metadata     TEXT NOT NULL DEFAULT '{}',
                    tenant_id    TEXT NOT NULL DEFAULT '',
                    created_at   REAL NOT NULL DEFAULT 0.0,
                    status       TEXT NOT NULL DEFAULT 'draft'
                )
                """
            )
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                CREATE TABLE IF NOT EXISTS chain_execution_log (
                    execution_id   TEXT PRIMARY KEY,
                    chain_id       TEXT NOT NULL,
                    success        INTEGER NOT NULL DEFAULT 0,
                    step_results   TEXT NOT NULL DEFAULT '[]',
                    total_duration_ms INTEGER NOT NULL DEFAULT 0,
                    failed_step    TEXT,
                    error          TEXT,
                    executed_at    REAL NOT NULL DEFAULT 0.0
                )
                """
            )
            conn.commit()

    def _load_chains(self) -> None:
        """Load persisted chains from SQLite."""
        with sqlite3.connect(_DB_PATH) as conn:
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT chain_id, name, description, steps, metadata, "
                "tenant_id, created_at, status FROM composed_chains"
            ).fetchall()

        for row in rows:
            chain_id = row[0]
            try:
                chain = ComposedChain(
                    chain_id=chain_id,
                    name=row[1],
                    description=row[2],
                    steps=self._deserialize_steps(json.loads(row[3]) if row[3] else []),
                    metadata=json.loads(row[4]) if row[4] else {},
                    tenant_id=row[5],
                    created_at=row[6],
                    status=ChainStatus(row[7]) if row[7] else ChainStatus.DRAFT,
                )
                self._chains[chain_id] = chain
            except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
                logger.warning("Failed to load chain %s: %s", chain_id, exc)

    @staticmethod
    def _serialize_steps(steps: list[ChainStep]) -> str:
        return json.dumps([
            {
                "step_id": s.step_id,
                "step_type": s.step_type.value if isinstance(s.step_type, ChainStepType) else s.step_type,
                "config": s.config,
                "next_step_id": s.next_step_id,
                "condition_expr": s.condition_expr,
                "timeout_ms": s.timeout_ms,
                "retry_count": s.retry_count,
            }
            for s in steps
        ])

    @staticmethod
    def _deserialize_steps(raw: list[dict[str, Any]]) -> list[ChainStep]:
        result: list[ChainStep] = []
        for s in raw:
            step_type_raw = s.get("step_type", "action")
            try:
                step_type = ChainStepType(step_type_raw)
            except ValueError:
                step_type = ChainStepType.ACTION
            result.append(ChainStep(
                step_id=s.get("step_id", ""),
                step_type=step_type,
                config=s.get("config", {}),
                next_step_id=s.get("next_step_id", ""),
                condition_expr=s.get("condition_expr", ""),
                timeout_ms=s.get("timeout_ms", 30000),
                retry_count=s.get("retry_count", 3),
            ))
        return result

    def _save_chain(self, chain: ComposedChain) -> None:
        """Persist a single chain to SQLite."""
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                INSERT OR REPLACE INTO composed_chains
                    (chain_id, name, description, steps, metadata,
                     tenant_id, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chain.chain_id,
                    chain.name,
                    chain.description,
                    self._serialize_steps(chain.steps),
                    json.dumps(chain.metadata),
                    chain.tenant_id,
                    chain.created_at,
                    chain.status.value if isinstance(chain.status, ChainStatus) else chain.status,
                ),
            )
            conn.commit()

    def _log_execution(self, result: ChainExecutionResult) -> None:
        """Record execution result to DB."""
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                INSERT INTO chain_execution_log
                    (execution_id, chain_id, success, step_results,
                     total_duration_ms, failed_step, error, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    result.chain_id,
                    1 if result.success else 0,
                    json.dumps([
                        {
                            "step_id": sr.step_id,
                            "success": sr.success,
                            "output": sr.output,
                            "duration_ms": sr.duration_ms,
                            "retry_count": sr.retry_count,
                            "error": sr.error,
                        }
                        for sr in result.step_results
                    ]),
                    result.total_duration_ms,
                    result.failed_step,
                    result.error,
                    time.time(),
                ),
            )
            conn.commit()

    # ------------------------------------------------------------------
    #  Composition
    # ------------------------------------------------------------------

    def compose_from_event(
        self,
        event_type: str,
        event_data: dict[str, Any],
        tenant_id: str,
    ) -> ComposedChain | None:
        """Given an event, select and compose relevant chain templates.

        Looks up templates matching the event pattern, tries each one
        (injecting event_type into variables), and returns the first
        successfully instantiated chain.  Returns None if no template
        can be instantiated.
        """
        with self._lock:
            templates = self.template_library.find_templates_for_event(event_type)
            if not templates:
                logger.info("No templates found for event_type=%s", event_type)
                return None

            # Inject event_type into variables so templates can use it
            enriched_data = {**event_data, "event_type": event_type}

            # Try each matching template until one instantiates successfully
            for template in templates:
                logger.info(
                    "Composing chain from event '%s' using template '%s'",
                    event_type, template.template_id,
                )
                try:
                    chain = self.template_library.instantiate(
                        template.template_id, enriched_data,
                    )
                except (KeyError, ValueError) as exc:
                    logger.debug(
                        "Template %s skipped for event '%s': %s",
                        template.template_id, event_type, exc,
                    )
                    continue

                chain.tenant_id = tenant_id
                chain.status = ChainStatus.READY
                self._chains[chain.chain_id] = chain
                self._save_chain(chain)
                return chain

            logger.warning("No template could be instantiated for event '%s'", event_type)
            return None

    def compose_from_intent(
        self,
        intent: str,
        context: dict[str, Any],
        tenant_id: str,
    ) -> ComposedChain | None:
        """Compose a chain from a natural language intent.

        Uses keyword matching to find templates, tries each one until
        instantiation succeeds, and returns the resulting chain.
        """
        with self._lock:
            templates = self.template_library.find_templates_for_intent(intent)
            if not templates:
                logger.info("No templates found for intent: %s", intent)
                return None

            # Try each matching template (sorted by relevance)
            for template in templates:
                logger.info(
                    "Composing chain from intent using template '%s'",
                    template.template_id,
                )
                try:
                    chain = self.template_library.instantiate(
                        template.template_id, context,
                    )
                except (KeyError, ValueError) as exc:
                    logger.debug(
                        "Template %s skipped for intent: %s",
                        template.template_id, exc,
                    )
                    continue

                chain.tenant_id = tenant_id
                chain.status = ChainStatus.READY
                self._chains[chain.chain_id] = chain
                self._save_chain(chain)
                return chain

            logger.warning("No template could be instantiated for intent: %s", intent)
            return None

    # ------------------------------------------------------------------
    #  Validation
    # ------------------------------------------------------------------

    def validate_chain(self, chain: ComposedChain) -> ChainValidationResult:
        """Validate a composed chain before execution.

        Checks:
          - Chain has at least one step
          - Step IDs are unique
          - Step types are valid
          - next_step_id references exist (or are empty)
          - No orphan steps (all reachable from first step)
          - Warnings for very long chains or missing conditions on branches
        """
        result = ChainValidationResult(valid=True, errors=[], warnings=[])

        # 1. Empty chain
        if not chain.steps:
            result.errors.append("Chain has no steps")
            result.valid = False
            return result

        # 2. Unique step IDs
        step_ids = {s.step_id for s in chain.steps}
        if len(step_ids) != len(chain.steps):
            result.errors.append("Duplicate step IDs detected")
            result.valid = False

        # 3. Valid step types
        for step in chain.steps:
            if not isinstance(step.step_type, ChainStepType):
                try:
                    ChainStepType(step.step_type)
                except ValueError:
                    result.errors.append(
                        f"Step '{step.step_id}' has invalid step_type: {step.step_type}"
                    )
                    result.valid = False

        # 4. next_step_id references
        for step in chain.steps:
            if step.next_step_id and step.next_step_id not in step_ids:
                result.errors.append(
                    f"Step '{step.step_id}' references non-existent next_step_id '{step.next_step_id}'"
                )
                result.valid = False

        # 5. Orphan detection (BFS from first step)
        if chain.steps:
            first_id = chain.steps[0].step_id
            visited: set[str] = set()
            queue = [first_id]
            steps_by_id = {s.step_id: s for s in chain.steps}
            while queue:
                current_id = queue.pop(0)
                if current_id in visited or current_id not in steps_by_id:
                    continue
                visited.add(current_id)
                nxt = steps_by_id[current_id].next_step_id
                if nxt:
                    queue.append(nxt)
            orphans = step_ids - visited
            if orphans:
                result.warnings.append(
                    f"Orphan steps not reachable from first step: {orphans}"
                )

        # 6. Length warning
        if len(chain.steps) > 10:
            result.warnings.append(
                f"Chain has {len(chain.steps)} steps — consider splitting into sub-chains"
            )

        # 7. Condition step without condition_expr
        for step in chain.steps:
            if step.step_type == ChainStepType.CONDITION and not step.condition_expr:
                result.warnings.append(
                    f"Condition step '{step.step_id}' has no condition_expr"
                )

        if result.errors:
            result.valid = False

        return result

    # ------------------------------------------------------------------
    #  Execution
    # ------------------------------------------------------------------

    def execute_chain(self, chain: ComposedChain) -> ChainExecutionResult:
        """Execute a composed chain step by step with retry and backoff.

        Sequential execution: each step's output feeds into the next
        step's context. On failure, retries with exponential backoff.
        If a step exhausts retries, the chain is marked as failed.
        """
        start_time = time.monotonic()
        step_results: list[ChainStepResult] = []
        context: dict[str, Any] = {}

        with self._lock:
            # Mark chain as executing
            chain.status = ChainStatus.EXECUTING
            self._save_chain(chain)

        steps_by_id = {s.step_id: s for s in chain.steps}
        if not chain.steps:
            result = ChainExecutionResult(
                chain_id=chain.chain_id,
                success=False,
                step_results=[],
                total_duration_ms=0,
                failed_step=None,
                error="Chain has no steps to execute",
            )
            with self._lock:
                chain.status = ChainStatus.FAILED
                self._save_chain(chain)
            self._log_execution(result)
            return result

        # Start from the first step
        current_step = chain.steps[0]
        visited: set[str] = set()

        while current_step is not None:
            if current_step.step_id in visited and current_step.next_step_id:
                # Loop detection
                result = ChainExecutionResult(
                    chain_id=chain.chain_id,
                    success=False,
                    step_results=step_results,
                    total_duration_ms=int((time.monotonic() - start_time) * 1000),
                    failed_step=current_step.step_id,
                    error=f"Loop detected at step '{current_step.step_id}'",
                )
                with self._lock:
                    chain.status = ChainStatus.FAILED
                    self._save_chain(chain)
                self._log_execution(result)
                return result

            visited.add(current_step.step_id)
            step_result = self._execute_step_with_retry(current_step, context)
            step_results.append(step_result)

            if not step_result.success:
                # Chain failed
                elapsed_ms = int((time.monotonic() - start_time) * 1000)
                result = ChainExecutionResult(
                    chain_id=chain.chain_id,
                    success=False,
                    step_results=step_results,
                    total_duration_ms=elapsed_ms,
                    failed_step=current_step.step_id,
                    error=step_result.error,
                )
                with self._lock:
                    chain.status = ChainStatus.FAILED
                    self._save_chain(chain)
                self._log_execution(result)
                return result

            # Merge step output into context
            context.update(step_result.output)

            # Determine next step
            next_id = current_step.next_step_id
            if next_id and next_id in steps_by_id:
                current_step = steps_by_id[next_id]
            else:
                current_step = None

        # All steps completed
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        result = ChainExecutionResult(
            chain_id=chain.chain_id,
            success=True,
            step_results=step_results,
            total_duration_ms=elapsed_ms,
            failed_step=None,
            error=None,
        )
        with self._lock:
            chain.status = ChainStatus.COMPLETED
            self._save_chain(chain)
        self._log_execution(result)
        logger.info(
            "Chain %s completed successfully in %dms (%d steps)",
            chain.chain_id, elapsed_ms, len(step_results),
        )
        return result

    def _execute_step_with_retry(
        self,
        step: ChainStep,
        context: dict[str, Any],
    ) -> ChainStepResult:
        """Execute a single step with exponential-backoff retry."""
        executor = _STEP_EXECUTORS.get(step.step_type)
        if executor is None:
            return ChainStepResult(
                step_id=step.step_id,
                success=False,
                output={},
                duration_ms=0,
                retry_count=0,
                error=f"No executor for step_type '{step.step_type}'",
            )

        max_retries = max(step.retry_count, 1)
        base_delay = 0.1  # 100ms base
        last_error: str | None = None

        for attempt in range(1, max_retries + 1):
            step_start = time.monotonic()
            try:
                output = executor(step.config, context)
                duration_ms = int((time.monotonic() - step_start) * 1000)

                # Check if the step self-reported failure
                if isinstance(output, dict) and output.get("passed") is False:
                    last_error = output.get("details", "Step reported failure")
                    if attempt < max_retries:
                        delay = base_delay * (2 ** (attempt - 1))
                        logger.debug(
                            "Step %s failed (attempt %d/%d): %s — retrying in %.2fs",
                            step.step_id, attempt, max_retries, last_error, delay,
                        )
                        time.sleep(delay)
                        continue

                    return ChainStepResult(
                        step_id=step.step_id,
                        success=False,
                        output=output,
                        duration_ms=duration_ms,
                        retry_count=attempt,
                        error=last_error,
                    )

                return ChainStepResult(
                    step_id=step.step_id,
                    success=True,
                    output=output if isinstance(output, dict) else {"result": output},
                    duration_ms=duration_ms,
                    retry_count=attempt,
                    error=None,
                )

            except Exception as exc:
                last_error = str(exc)
                duration_ms = int((time.monotonic() - step_start) * 1000)
                if attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.debug(
                        "Step %s error (attempt %d/%d): %s — retrying in %.2fs",
                        step.step_id, attempt, max_retries, exc, delay,
                    )
                    time.sleep(delay)
                else:
                    logger.warning(
                        "Step %s failed after %d attempts: %s",
                        step.step_id, max_retries, exc,
                    )

        return ChainStepResult(
            step_id=step.step_id,
            success=False,
            output={},
            duration_ms=0,
            retry_count=max_retries,
            error=last_error,
        )

    # ------------------------------------------------------------------
    #  Query
    # ------------------------------------------------------------------

    def get_chain(self, chain_id: str) -> ComposedChain | None:
        """Retrieve a composed chain by ID."""
        with self._lock:
            return self._chains.get(chain_id)

    def list_chains(self, tenant_id: str | None = None) -> list[ComposedChain]:
        """List chains, optionally filtered by tenant."""
        with self._lock:
            chains = list(self._chains.values())
        if tenant_id:
            chains = [c for c in chains if c.tenant_id == tenant_id]
        return sorted(chains, key=lambda c: c.created_at, reverse=True)


# ---------------------------------------------------------------------------
#  Singleton
# ---------------------------------------------------------------------------

_instance: DynamicChainComposer | None = None
_instance_lock = threading.Lock()


def get_chain_composer() -> DynamicChainComposer:
    """Return the DynamicChainComposer singleton (thread-safe)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DynamicChainComposer()
    return _instance


__all__ = [
    "ChainStep",
    "ChainStepType",
    "ChainStatus",
    "ComposedChain",
    "ChainStepResult",
    "ChainExecutionResult",
    "ChainValidationResult",
    "DynamicChainComposer",
    "get_chain_composer",
]
