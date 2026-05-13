"""Saga - Sync Execution Mixin."""

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from ._types import SagaStatus, SagaStep, SagaContext

logger = logging.getLogger("zenic_agents.patterns.orchestration.saga")


class SagaSyncMixin:
    """Mixin providing synchronous saga execution and step helpers."""

    # ----------------------------------------------------------
    #  SYNC EXECUTION
    # ----------------------------------------------------------

    def execute(self, context: Optional[SagaContext] = None) -> SagaContext:
        """
        Execute all saga steps sequentially with automatic compensation.

        If any step fails (raises or times out), all previously completed
        steps are compensated in REVERSE order. The saga status transitions
        through: PENDING -> RUNNING -> COMPLETED (or COMPENSATING ->
        COMPENSATED/FAILED).

        Args:
            context: Optional pre-populated SagaContext. If None,
                     a new one is created with a generated saga_id.

        Returns:
            The SagaContext with results, errors, and state after
            execution (and possible compensation).
        """
        start_time = time.time()

        # Initialize context if not provided
        if context is None:
            context = SagaContext(saga_id=self._saga_id, steps=self._steps)

        with self._lock:
            self._execution_count += 1
            self._status = SagaStatus.RUNNING

        logger.info(
            "Saga[%s]: Starting execution (saga_id=%s, steps=%d)",
            self._name, context.saga_id[:8], len(self._steps),
        )

        try:
            for step in self._steps:
                self._execute_step(step, context)

            # All steps succeeded
            with self._lock:
                self._status = SagaStatus.COMPLETED
                self._last_execution_time_ms = (time.time() - start_time) * 1000

            logger.info(
                "Saga[%s]: Completed successfully (saga_id=%s, "
                "steps=%d, time=%.1fms)",
                self._name, context.saga_id[:8], len(self._steps),
                self._last_execution_time_ms,
            )

        except Exception as exc:
            logger.error(
                "Saga[%s]: Step failed (saga_id=%s): %s",
                self._name, context.saga_id[:8], exc,
            )
            context.add_error(str(exc))

            with self._lock:
                self._error_count += 1
                self._status = SagaStatus.COMPENSATING

            # Compensate completed steps in reverse order
            self._compensate(context)

        return context

    # ----------------------------------------------------------
    #  ASYNC EXECUTION
    # ----------------------------------------------------------

    async def execute_async(
        self, context: Optional[SagaContext] = None
    ) -> SagaContext:
        """
        Asynchronously execute all saga steps with automatic compensation.

        Same semantics as execute() but supports async step actions.
        Sync actions are automatically wrapped.

        Args:
            context: Optional pre-populated SagaContext.

        Returns:
            The SagaContext with results, errors, and state.
        """
        start_time = time.time()

        if context is None:
            context = SagaContext(saga_id=self._saga_id, steps=self._steps)

        with self._lock:
            self._execution_count += 1
            self._status = SagaStatus.RUNNING

        logger.info(
            "Saga[%s][async]: Starting execution (saga_id=%s, steps=%d)",
            self._name, context.saga_id[:8], len(self._steps),
        )

        try:
            for step in self._steps:
                await self._execute_step_async(step, context)

            with self._lock:
                self._status = SagaStatus.COMPLETED
                self._last_execution_time_ms = (time.time() - start_time) * 1000

            logger.info(
                "Saga[%s][async]: Completed successfully (saga_id=%s, "
                "time=%.1fms)",
                self._name, context.saga_id[:8],
                self._last_execution_time_ms,
            )

        except Exception as exc:
            logger.error(
                "Saga[%s][async]: Step failed (saga_id=%s): %s",
                self._name, context.saga_id[:8], exc,
            )
            context.add_error(str(exc))

            with self._lock:
                self._error_count += 1
                self._status = SagaStatus.COMPENSATING

            await self._compensate_async(context)

        return context

    # ----------------------------------------------------------
    #  STEP EXECUTION (SYNC)
    # ----------------------------------------------------------

    def _execute_step(self, step: SagaStep, context: SagaContext) -> None:
        """
        Execute a single saga step with optional timeout.

        Args:
            step: The SagaStep to execute.
            context: The shared SagaContext.

        Raises:
            Exception: If the step action raises or times out.
        """
        logger.info(
            "Saga[%s]: Executing step '%s' (timeout=%s)",
            self._name, step.name,
            f"{step.timeout}s" if step.timeout else "none",
        )

        if step.timeout is not None:
            self._execute_step_with_timeout(step, context)
        else:
            result = step.action(context)
            context.results[step.name] = result
            context.mark_step_completed(step)

        logger.info(
            "Saga[%s]: Step '%s' completed successfully",
            self._name, step.name,
        )

    def _execute_step_with_timeout(
        self, step: SagaStep, context: SagaContext
    ) -> None:
        """
        Execute a step with timeout enforcement.

        Uses a threading-based timeout mechanism since the step action
        may not be async-aware.

        Args:
            step: The SagaStep with timeout set.
            context: The shared SagaContext.

        Raises:
            TimeoutError: If the step exceeds its timeout.
        """
        result_holder: Dict[str, Any] = {"result": None, "error": None}

        def _target() -> None:
            try:
                result_holder["result"] = step.action(context)
            except Exception as exc:
                result_holder["error"] = exc

        worker = threading.Thread(target=_target, daemon=True)
        worker.start()
        worker.join(timeout=step.timeout)

        if worker.is_alive():
            # Thread is still running; it timed out
            raise TimeoutError(
                f"Saga step '{step.name}' exceeded timeout of "
                f"{step.timeout}s"
            )

        if result_holder["error"] is not None:
            raise result_holder["error"]

        context.results[step.name] = result_holder["result"]
        context.mark_step_completed(step)
