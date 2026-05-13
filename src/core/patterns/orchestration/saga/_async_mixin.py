"""Saga - Async Execution Mixin."""

import asyncio
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from ._types import SagaStatus, SagaStep, SagaContext

logger = logging.getLogger("zenic_agents.patterns.orchestration.saga")


class SagaAsyncMixin:
    """Mixin providing asynchronous saga execution."""


    # ----------------------------------------------------------
    #  STEP EXECUTION (ASYNC)
    # ----------------------------------------------------------

    async def _execute_step_async(
        self, step: SagaStep, context: SagaContext
    ) -> None:
        """
        Asynchronously execute a single saga step with optional timeout.

        Args:
            step: The SagaStep to execute.
            context: The shared SagaContext.

        Raises:
            Exception: If the step action raises or times out.
        """
        logger.info(
            "Saga[%s][async]: Executing step '%s'",
            self._name, step.name,
        )

        try:
            if step.timeout is not None:
                result = await asyncio.wait_for(
                    self._call_action_async(step.action, context),
                    timeout=step.timeout,
                )
            else:
                result = await self._call_action_async(step.action, context)

            context.results[step.name] = result
            context.mark_step_completed(step)

        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Saga step '{step.name}' exceeded timeout of "
                f"{step.timeout}s"
            )

        logger.info(
            "Saga[%s][async]: Step '%s' completed successfully",
            self._name, step.name,
        )

    async def _call_action_async(
        self, action: Callable[[Any], Any], context: SagaContext
    ) -> Any:
        """
        Call an action, handling both sync and async callables.

        Args:
            action: The step action callable.
            context: The shared SagaContext.

        Returns:
            The result of the action.
        """
        result = action(context)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    # ----------------------------------------------------------
    #  COMPENSATION (SYNC)
    # ----------------------------------------------------------

    def _compensate(self, context: SagaContext) -> None:
        """
        Run compensations for all completed steps in REVERSE order.

        Compensation failures are logged but do not stop the
        compensation process — all completed steps will have their
        compensations attempted.

        Args:
            context: The SagaContext with completed steps.
        """
        completed = context.completed_steps
        if not completed:
            logger.info(
                "Saga[%s]: No steps to compensate", self._name,
            )
            with self._lock:
                self._status = SagaStatus.FAILED
            return

        logger.info(
            "Saga[%s]: Compensating %d steps in reverse order",
            self._name, len(completed),
        )

        compensation_errors: List[str] = []

        # Reverse order compensation
        for step in reversed(completed):
            if step.compensation is not None:
                logger.info(
                    "Saga[%s]: Compensating step '%s'",
                    self._name, step.name,
                )
                try:
                    if step.timeout is not None:
                        self._compensate_step_with_timeout(step, context)
                    else:
                        step.compensation(context)

                    with self._lock:
                        self._compensation_count += 1

                    logger.info(
                        "Saga[%s]: Step '%s' compensated successfully",
                        self._name, step.name,
                    )
                except Exception as exc:
                    error_msg = (
                        f"Compensation failed for step '{step.name}': {exc}"
                    )
                    compensation_errors.append(error_msg)
                    context.add_error(error_msg)
                    with self._lock:
                        self._error_count += 1
                    logger.error(
                        "Saga[%s]: %s", self._name, error_msg,
                        exc_info=True,
                    )
            else:
                logger.warning(
                    "Saga[%s]: Step '%s' has no compensation defined",
                    self._name, step.name,
                )

        # Determine final status
        with self._lock:
            if compensation_errors:
                self._status = SagaStatus.FAILED
            else:
                self._status = SagaStatus.COMPENSATED

        final_status = self._status
        logger.info(
            "Saga[%s]: Compensation complete (status=%s, errors=%d)",
            self._name, final_status.value, len(compensation_errors),
        )

    def _compensate_step_with_timeout(
        self, step: SagaStep, context: SagaContext
    ) -> None:
        """
        Run a step's compensation with timeout enforcement.

        Args:
            step: The SagaStep with compensation and timeout.
            context: The shared SagaContext.

        Raises:
            TimeoutError: If compensation exceeds timeout.
        """
        if step.compensation is None:
            return

        error_holder: Dict[str, Any] = {"error": None}

        def _target() -> None:
            try:
                step.compensation(context)  # type: ignore[misc]
            except Exception as exc:
                error_holder["error"] = exc

        worker = threading.Thread(target=_target, daemon=True)
        worker.start()
        worker.join(timeout=step.timeout)

        if worker.is_alive():
            raise TimeoutError(
                f"Compensation for step '{step.name}' exceeded timeout "
                f"of {step.timeout}s"
            )

        if error_holder["error"] is not None:
            raise error_holder["error"]

    # ----------------------------------------------------------
    #  COMPENSATION (ASYNC)
    # ----------------------------------------------------------

    async def _compensate_async(self, context: SagaContext) -> None:
        """
        Asynchronously run compensations for all completed steps.

        Same semantics as _compensate() but supports async compensation
        callables.

        Args:
            context: The SagaContext with completed steps.
        """
        completed = context.completed_steps
        if not completed:
            with self._lock:
                self._status = SagaStatus.FAILED
            return

        logger.info(
            "Saga[%s][async]: Compensating %d steps in reverse order",
            self._name, len(completed),
        )

        compensation_errors: List[str] = []

        for step in reversed(completed):
            if step.compensation is not None:
                logger.info(
                    "Saga[%s][async]: Compensating step '%s'",
                    self._name, step.name,
                )
                try:
                    if step.timeout is not None:
                        await asyncio.wait_for(
                            self._call_action_async(
                                step.compensation, context
                            ),
                            timeout=step.timeout,
                        )
                    else:
                        await self._call_action_async(
                            step.compensation, context
                        )

                    with self._lock:
                        self._compensation_count += 1

                except asyncio.TimeoutError:
                    error_msg = (
                        f"Compensation timeout for step '{step.name}'"
                    )
                    compensation_errors.append(error_msg)
                    context.add_error(error_msg)
                    with self._lock:
                        self._error_count += 1

                except Exception as exc:
                    error_msg = (
                        f"Compensation failed for step '{step.name}': {exc}"
                    )
                    compensation_errors.append(error_msg)
                    context.add_error(error_msg)
                    with self._lock:
                        self._error_count += 1
                    logger.error(
                        "Saga[%s][async]: %s", self._name, error_msg,
                    )
            else:
                logger.warning(
                    "Saga[%s][async]: Step '%s' has no compensation",
                    self._name, step.name,
                )

        with self._lock:
            if compensation_errors:
                self._status = SagaStatus.FAILED
            else:
                self._status = SagaStatus.COMPENSATED

        logger.info(
            "Saga[%s][async]: Compensation complete (status=%s)",
            self._name, self._status.value,
        )
