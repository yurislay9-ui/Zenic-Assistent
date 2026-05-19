"""
ZENIC-AGENTS — DynamicChainComposer: composes & executes workflow chains.

Dynamically selects chain templates from events or natural-language
intents, instantiates them, validates, and executes step by step with
retry logic and exponential backoff.

Thread-safe via RLock. Persisted to SQLite (chain_composer.sqlite).
DB operations delegated to _db_layer.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from ._optimizer import _STEP_EXECUTORS
from ._types import (
    _DB_DIR,
    _DB_PATH,
    ChainExecutionResult,
    ChainStatus,
    ChainStep,
    ChainStepResult,
    ChainValidationResult,
    ComposedChain,
)
from ._validator import validate_chain
from ._db_layer import (
    init_db as _init_db,
    load_chains as _load_chains,
    save_chain as _save_chain,
    log_execution as _log_execution,
)

logger = logging.getLogger(__name__)


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
        _init_db(_DB_PATH)
        self._chains = _load_chains(_DB_PATH)

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
            from ..chain_templates import get_template_library
            self._template_library = get_template_library()
        return self._template_library

    # ------------------------------------------------------------------
    #  Composition
    # ------------------------------------------------------------------

    def compose_from_event(
        self,
        event_type: str,
        event_data: dict[str, Any],
        tenant_id: str,
    ) -> ComposedChain | None:
        """Given an event, select and compose relevant chain templates."""
        with self._lock:
            templates = self.template_library.find_templates_for_event(event_type)
            if not templates:
                logger.info("No templates found for event_type=%s", event_type)
                return None

            enriched_data = {**event_data, "event_type": event_type}

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
                _save_chain(chain, _DB_PATH)
                return chain

            logger.warning("No template could be instantiated for event '%s'", event_type)
            return None

    def compose_from_intent(
        self,
        intent: str,
        context: dict[str, Any],
        tenant_id: str,
    ) -> ComposedChain | None:
        """Compose a chain from a natural language intent."""
        with self._lock:
            templates = self.template_library.find_templates_for_intent(intent)
            if not templates:
                logger.info("No templates found for intent: %s", intent)
                return None

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
                _save_chain(chain, _DB_PATH)
                return chain

            logger.warning("No template could be instantiated for intent: %s", intent)
            return None

    # ------------------------------------------------------------------
    #  Validation (delegates to standalone function)
    # ------------------------------------------------------------------

    def validate_chain(self, chain: ComposedChain) -> ChainValidationResult:
        """Validate a composed chain before execution.

        Delegates to the standalone :func:`validate_chain` in
        ``_validator.py``.
        """
        return validate_chain(chain)

    # ------------------------------------------------------------------
    #  Execution
    # ------------------------------------------------------------------

    def execute_chain(self, chain: ComposedChain) -> ChainExecutionResult:
        """Execute a composed chain step by step with retry and backoff."""
        start_time = time.monotonic()
        step_results: list[ChainStepResult] = []
        context: dict[str, Any] = {}

        with self._lock:
            chain.status = ChainStatus.EXECUTING
            _save_chain(chain, _DB_PATH)

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
                _save_chain(chain, _DB_PATH)
            _log_execution(result, _DB_PATH)
            return result

        current_step = chain.steps[0]
        visited: set[str] = set()

        while current_step is not None:
            if current_step.step_id in visited and current_step.next_step_id:
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
                    _save_chain(chain, _DB_PATH)
                _log_execution(result, _DB_PATH)
                return result

            visited.add(current_step.step_id)
            step_result = self._execute_step_with_retry(current_step, context)
            step_results.append(step_result)

            if not step_result.success:
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
                    _save_chain(chain, _DB_PATH)
                _log_execution(result, _DB_PATH)
                return result

            context.update(step_result.output)

            next_id = current_step.next_step_id
            if next_id and next_id in steps_by_id:
                current_step = steps_by_id[next_id]
            else:
                current_step = None

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
            _save_chain(chain, _DB_PATH)
        _log_execution(result, _DB_PATH)
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
