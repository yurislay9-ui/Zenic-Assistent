"""
Step Executor — Step execution engine for pipeline orchestration.

Provides a step execution engine that runs pipeline steps with
timeout support, retry logic, and result collection.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
No external dependencies beyond Python stdlib.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

__all__ = [
    "StepStatus",
    "StepResult",
    "StepExecutor",
]


# ──────────────────────────────────────────────────────────────
#  DATA CONTRACTS
# ──────────────────────────────────────────────────────────────

class StepStatus(str, Enum):
    """Status of a pipeline step execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    RETRYING = "retrying"


@dataclass
class StepResult:
    """
    Result of a step execution.

    Attributes:
        step_id: Unique identifier for the step.
        status: Final status of the execution.
        output: Output data from the step (if successful).
        error: Error message or exception info (if failed).
        duration_ms: Execution duration in milliseconds.
        attempts: Number of execution attempts.
        metadata: Additional metadata.
    """
    step_id: str
    status: StepStatus = StepStatus.PENDING
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    attempts: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
#  STEP EXECUTOR
# ──────────────────────────────────────────────────────────────

# Type alias for step callables
StepCallable = Callable[..., Any]
AsyncStepCallable = Callable[..., Any]


class StepExecutor:
    """
    Step execution engine for pipeline orchestration.

    Supports:
    - Synchronous and asynchronous step execution
    - Configurable retries with backoff
    - Timeout enforcement
    - Result collection and error handling

    Usage::

        executor = StepExecutor(max_retries=3, default_timeout=30.0)

        def my_step(data):
            return {"result": data["value"] * 2}

        result = executor.execute("step_1", my_step, {"value": 21})
        # result.status == StepStatus.COMPLETED
        # result.output == {"result": 42}

    Thread Safety:
        This class is NOT thread-safe. External synchronization is required
        for concurrent access.
    """

    def __init__(
        self,
        max_retries: int = 0,
        default_timeout: Optional[float] = None,
        backoff_base: float = 1.0,
    ) -> None:
        """
        Initialize the StepExecutor.

        Args:
            max_retries: Maximum number of retry attempts on failure.
            default_timeout: Default timeout in seconds (None = no timeout).
            backoff_base: Base for exponential backoff (seconds).
        """
        self._max_retries = max_retries
        self._default_timeout = default_timeout
        self._backoff_base = backoff_base
        self._results: Dict[str, StepResult] = {}
        self._execution_count: int = 0
        self._error_count: int = 0

    # ── Synchronous Execution ────────────────────────────────

    def execute(
        self,
        step_id: str,
        step_fn: StepCallable,
        input_data: Any = None,
        timeout: Optional[float] = None,
        retries: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StepResult:
        """
        Execute a synchronous step.

        Args:
            step_id: Unique identifier for this step execution.
            step_fn: The callable to execute.
            input_data: Input data passed to the step function.
            timeout: Timeout in seconds (overrides default).
            retries: Max retries for this step (overrides default).
            metadata: Additional metadata to attach to the result.

        Returns:
            StepResult with execution outcome.
        """
        effective_timeout = timeout if timeout is not None else self._default_timeout
        effective_retries = retries if retries is not None else self._max_retries
        result = StepResult(
            step_id=step_id,
            status=StepStatus.PENDING,
            metadata=metadata or {},
        )

        last_error: Optional[str] = None
        for attempt in range(1, effective_retries + 2):  # +1 for initial attempt
            result.attempts = attempt
            start = time.monotonic()
            try:
                output = step_fn(input_data)
                result.status = StepStatus.COMPLETED
                result.output = output
                result.duration_ms = (time.monotonic() - start) * 1000
                self._execution_count += 1
                logger.debug(
                    "StepExecutor: Step '%s' completed in %.1fms (attempt %d)",
                    step_id, result.duration_ms, attempt,
                )
                break
            except Exception as exc:
                last_error = str(exc)
                result.duration_ms = (time.monotonic() - start) * 1000
                if attempt <= effective_retries:
                    result.status = StepStatus.RETRYING
                    backoff = self._backoff_base * (2 ** (attempt - 1))
                    logger.warning(
                        "StepExecutor: Step '%s' failed (attempt %d/%d), "
                        "retrying in %.1fs: %s",
                        step_id, attempt, effective_retries + 1, backoff, exc,
                    )
                    time.sleep(backoff)
                else:
                    result.status = StepStatus.FAILED
                    result.error = last_error
                    self._error_count += 1
                    self._execution_count += 1
                    logger.error(
                        "StepExecutor: Step '%s' FAILED after %d attempts: %s",
                        step_id, attempt, exc,
                    )

        self._results[step_id] = result
        return result

    # ── Asynchronous Execution ───────────────────────────────

    async def execute_async(
        self,
        step_id: str,
        step_fn: Union[StepCallable, AsyncStepCallable],
        input_data: Any = None,
        timeout: Optional[float] = None,
        retries: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StepResult:
        """
        Execute a step asynchronously.

        Supports both sync and async callables. Sync callables are
        run in the default executor to avoid blocking the event loop.

        Args:
            step_id: Unique identifier for this step execution.
            step_fn: The callable to execute (sync or async).
            input_data: Input data passed to the step function.
            timeout: Timeout in seconds.
            retries: Max retries for this step.
            metadata: Additional metadata.

        Returns:
            StepResult with execution outcome.
        """
        effective_timeout = timeout if timeout is not None else self._default_timeout
        effective_retries = retries if retries is not None else self._max_retries
        result = StepResult(
            step_id=step_id,
            status=StepStatus.PENDING,
            metadata=metadata or {},
        )

        last_error: Optional[str] = None
        for attempt in range(1, effective_retries + 2):
            result.attempts = attempt
            start = time.monotonic()
            try:
                if asyncio.iscoroutinefunction(step_fn):
                    coro = step_fn(input_data)
                    if effective_timeout is not None:
                        output = await asyncio.wait_for(coro, timeout=effective_timeout)
                    else:
                        output = await coro
                else:
                    loop = asyncio.get_event_loop()
                    if effective_timeout is not None:
                        output = await asyncio.wait_for(
                            loop.run_in_executor(None, step_fn, input_data),
                            timeout=effective_timeout,
                        )
                    else:
                        output = await loop.run_in_executor(None, step_fn, input_data)

                result.status = StepStatus.COMPLETED
                result.output = output
                result.duration_ms = (time.monotonic() - start) * 1000
                self._execution_count += 1
                logger.debug(
                    "StepExecutor[async]: Step '%s' completed in %.1fms",
                    step_id, result.duration_ms,
                )
                break

            except asyncio.TimeoutError:
                result.status = StepStatus.TIMED_OUT
                result.duration_ms = (time.monotonic() - start) * 1000
                result.error = f"Step timed out after {effective_timeout}s"
                self._error_count += 1
                self._execution_count += 1
                logger.error(
                    "StepExecutor[async]: Step '%s' TIMED OUT after %.1fs",
                    step_id, effective_timeout,
                )
                break

            except Exception as exc:
                last_error = str(exc)
                result.duration_ms = (time.monotonic() - start) * 1000
                if attempt <= effective_retries:
                    result.status = StepStatus.RETRYING
                    backoff = self._backoff_base * (2 ** (attempt - 1))
                    logger.warning(
                        "StepExecutor[async]: Step '%s' failed (attempt %d/%d): %s",
                        step_id, attempt, effective_retries + 1, exc,
                    )
                    await asyncio.sleep(backoff)
                else:
                    result.status = StepStatus.FAILED
                    result.error = last_error
                    self._error_count += 1
                    self._execution_count += 1
                    logger.error(
                        "StepExecutor[async]: Step '%s' FAILED after %d attempts: %s",
                        step_id, attempt, exc,
                    )

        self._results[step_id] = result
        return result

    # ── Batch Execution ──────────────────────────────────────

    def execute_batch(
        self,
        steps: List[Dict[str, Any]],
    ) -> List[StepResult]:
        """
        Execute a batch of steps sequentially.

        Args:
            steps: List of dicts with keys: step_id, step_fn, input_data,
                   timeout, retries, metadata.

        Returns:
            List of StepResult objects in the same order.
        """
        results: List[StepResult] = []
        for step_spec in steps:
            result = self.execute(
                step_id=step_spec["step_id"],
                step_fn=step_spec["step_fn"],
                input_data=step_spec.get("input_data"),
                timeout=step_spec.get("timeout"),
                retries=step_spec.get("retries"),
                metadata=step_spec.get("metadata"),
            )
            results.append(result)
        return results

    async def execute_batch_async(
        self,
        steps: List[Dict[str, Any]],
        max_concurrency: int = 4,
    ) -> List[StepResult]:
        """
        Execute a batch of steps concurrently with bounded concurrency.

        Args:
            steps: List of step specifications.
            max_concurrency: Maximum number of concurrent executions.

        Returns:
            List of StepResult objects in the same order.
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _run_step(spec: Dict[str, Any]) -> StepResult:
            async with semaphore:
                return await self.execute_async(
                    step_id=spec["step_id"],
                    step_fn=spec["step_fn"],
                    input_data=spec.get("input_data"),
                    timeout=spec.get("timeout"),
                    retries=spec.get("retries"),
                    metadata=spec.get("metadata"),
                )

        tasks = [_run_step(s) for s in steps]
        return await asyncio.gather(*tasks)

    # ── Accessors ────────────────────────────────────────────

    def get_result(self, step_id: str) -> Optional[StepResult]:
        """Retrieve the result of a previously executed step."""
        return self._results.get(step_id)

    @property
    def results(self) -> Dict[str, StepResult]:
        """All step results keyed by step_id."""
        return dict(self._results)

    @property
    def stats(self) -> Dict[str, Any]:
        """Runtime statistics."""
        return {
            "total_executions": self._execution_count,
            "total_errors": self._error_count,
            "results_stored": len(self._results),
        }

    def clear_results(self) -> None:
        """Clear all stored results."""
        self._results.clear()
