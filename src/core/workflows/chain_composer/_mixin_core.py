"""
chain_composer._mixin_core — Core composition, validation, and execution mixin.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.core.workflows.chain_composer._types import (
    ChainStep,
    ChainStepType,
    ChainStatus,
    ComposedChain,
    ChainStepResult,
    ChainExecutionResult,
    ChainValidationResult,
)
from src.core.workflows.chain_composer._executors import STEP_EXECUTORS

logger = logging.getLogger(__name__)


class CoreMixin:
    """Mixin providing core composition, validation, and execution methods."""

    # Provided by main class
    _lock: object
    _chains: dict[str, ComposedChain]
    _template_library: Any

    # ------------------------------------------------------------------
    #  Composition
    # ------------------------------------------------------------------

    def compose_from_event(
        self, event_type: str, event_data: dict[str, Any], tenant_id: str,
    ) -> ComposedChain | None:
        """Given an event, select and compose relevant chain templates."""
        with self._lock:
            templates = self.template_library.find_templates_for_event(event_type)
            if not templates:
                return None
            enriched_data = {**event_data, "event_type": event_type}
            for template in templates:
                try:
                    chain = self.template_library.instantiate(template.template_id, enriched_data)
                except (KeyError, ValueError):
                    continue
                chain.tenant_id = tenant_id
                chain.status = ChainStatus.READY
                self._chains[chain.chain_id] = chain
                self._save_chain(chain)
                return chain
            return None

    def compose_from_intent(
        self, intent: str, context: dict[str, Any], tenant_id: str,
    ) -> ComposedChain | None:
        """Compose a chain from a natural language intent."""
        with self._lock:
            templates = self.template_library.find_templates_for_intent(intent)
            if not templates:
                return None
            for template in templates:
                try:
                    chain = self.template_library.instantiate(template.template_id, context)
                except (KeyError, ValueError):
                    continue
                chain.tenant_id = tenant_id
                chain.status = ChainStatus.READY
                self._chains[chain.chain_id] = chain
                self._save_chain(chain)
                return chain
            return None

    # ------------------------------------------------------------------
    #  Validation
    # ------------------------------------------------------------------

    def validate_chain(self, chain: ComposedChain) -> ChainValidationResult:
        """Validate a composed chain before execution."""
        result = ChainValidationResult(valid=True, errors=[], warnings=[])

        if not chain.steps:
            result.errors.append("Chain has no steps")
            result.valid = False
            return result

        step_ids = {s.step_id for s in chain.steps}
        if len(step_ids) != len(chain.steps):
            result.errors.append("Duplicate step IDs detected")
            result.valid = False

        for step in chain.steps:
            if not isinstance(step.step_type, ChainStepType):
                try:
                    ChainStepType(step.step_type)
                except ValueError:
                    result.errors.append(f"Step '{step.step_id}' has invalid step_type: {step.step_type}")
                    result.valid = False

        for step in chain.steps:
            if step.next_step_id and step.next_step_id not in step_ids:
                result.errors.append(f"Step '{step.step_id}' references non-existent next_step_id '{step.next_step_id}'")
                result.valid = False

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
                result.warnings.append(f"Orphan steps not reachable from first step: {orphans}")

        if len(chain.steps) > 10:
            result.warnings.append(f"Chain has {len(chain.steps)} steps — consider splitting into sub-chains")

        for step in chain.steps:
            if step.step_type == ChainStepType.CONDITION and not step.condition_expr:
                result.warnings.append(f"Condition step '{step.step_id}' has no condition_expr")

        if result.errors:
            result.valid = False
        return result

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
            self._save_chain(chain)

        steps_by_id = {s.step_id: s for s in chain.steps}
        if not chain.steps:
            result = ChainExecutionResult(
                chain_id=chain.chain_id, success=False,
                error="Chain has no steps to execute",
            )
            with self._lock:
                chain.status = ChainStatus.FAILED
                self._save_chain(chain)
            self._log_execution(result)
            return result

        current_step = chain.steps[0]
        visited: set[str] = set()

        while current_step is not None:
            if current_step.step_id in visited and current_step.next_step_id:
                result = ChainExecutionResult(
                    chain_id=chain.chain_id, success=False,
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
                elapsed_ms = int((time.monotonic() - start_time) * 1000)
                result = ChainExecutionResult(
                    chain_id=chain.chain_id, success=False,
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

            context.update(step_result.output)
            next_id = current_step.next_step_id
            if next_id and next_id in steps_by_id:
                current_step = steps_by_id[next_id]
            else:
                current_step = None

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        result = ChainExecutionResult(
            chain_id=chain.chain_id, success=True,
            step_results=step_results, total_duration_ms=elapsed_ms,
        )
        with self._lock:
            chain.status = ChainStatus.COMPLETED
            self._save_chain(chain)
        self._log_execution(result)
        return result

    def _execute_step_with_retry(
        self, step: ChainStep, context: dict[str, Any],
    ) -> ChainStepResult:
        """Execute a single step with exponential-backoff retry."""
        executor = STEP_EXECUTORS.get(step.step_type)
        if executor is None:
            return ChainStepResult(
                step_id=step.step_id, success=False,
                error=f"No executor for step_type '{step.step_type}'",
            )

        max_retries = max(step.retry_count, 1)
        base_delay = 0.1
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
                        time.sleep(delay)
                        continue
                    return ChainStepResult(
                        step_id=step.step_id, success=False,
                        output=output, duration_ms=duration_ms,
                        retry_count=attempt, error=last_error,
                    )

                return ChainStepResult(
                    step_id=step.step_id, success=True,
                    output=output if isinstance(output, dict) else {"result": output},
                    duration_ms=duration_ms, retry_count=attempt,
                )

            except Exception as exc:
                last_error = str(exc)
                duration_ms = int((time.monotonic() - step_start) * 1000)
                if attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    time.sleep(delay)
                else:
                    logger.warning("Step %s failed after %d attempts: %s", step.step_id, max_retries, exc)

        return ChainStepResult(
            step_id=step.step_id, success=False,
            output={}, retry_count=max_retries, error=last_error,
        )
