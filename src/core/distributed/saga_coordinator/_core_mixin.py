"""DistributedSagaCoordinator - Core methods."""

import logging
import uuid
from typing import Any, Dict, List, Optional

from ._types import DistributedSagaState, DistributedSagaStep
from ..task_queue import TaskMessage, TaskPriority

# Phase 5: Audit logging
try:
    from src.core.observability.audit import get_audit_logger, AuditEventType, AuditSeverity
    _AUDIT_AVAILABLE = True
except ImportError:
    _AUDIT_AVAILABLE = False

logger = logging.getLogger("zenic_agents.distributed.saga_coordinator")

class DistributedSagaCoordinatorCoreMixin:
    """Core methods mixin — see DistributedSagaCoordinator for full docs."""

    async def start_saga(
        self,
        name: str,
        steps: List[DistributedSagaStep],
        initial_context: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> str:
        """
        Create and start a new distributed saga.

        Persists the saga definition to the backend, then dispatches
        the first step as a task to the queue.

        Args:
            name: Human-readable saga name.
            steps: Ordered list of saga step definitions.
            initial_context: Initial context data shared between steps.
            tenant_id: Optional tenant for multi-tenant isolation.
            correlation_id: Optional correlation ID for tracing.

        Returns:
            The saga_id of the newly created saga.

        Raises:
            ValueError: If name or steps is empty.
        """
        if not name:
            raise ValueError("Saga name must not be empty")
        if not steps:
            raise ValueError("Saga must have at least one step")

        saga_id = f"saga-{uuid.uuid4().hex[:12]}"
        context = initial_context or {}
        context["saga_id"] = saga_id
        context["correlation_id"] = correlation_id

        # Persist saga definition
        steps_data = [
            {
                "name": step.name,
                "action_task_type": step.action_task_type,
                "compensation_task_type": step.compensation_task_type,
                "timeout": step.timeout or self._default_step_timeout,
                "priority": step.priority,
            }
            for step in steps
        ]

        created = await self._backend.create_saga(
            saga_id=saga_id,
            name=name,
            steps=steps_data,
            initial_context=context,
        )

        if not created:
            raise RuntimeError(f"Failed to create saga {saga_id}")

        # Update status to RUNNING
        await self._backend.update_saga_status(saga_id, "RUNNING")

        # Dispatch first step
        first_step = steps[0]
        await self._dispatch_step(
            saga_id=saga_id,
            step=first_step,
            context=context,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
        )

        # Cache locally
        self._active_sagas[saga_id] = {
            "name": name,
            "steps": steps_data,
            "context": context,
            "current_step_index": 0,
            "tenant_id": tenant_id,
        }

        logger.info(
            "SagaCoordinator: Started saga %s (name=%s, steps=%d)",
            saga_id[:8], name, len(steps),
        )
        # Phase 5: Audit event
        if _AUDIT_AVAILABLE:
            try:
                audit = get_audit_logger()
                audit.log_event(
                    event_type=AuditEventType.SAGA_STARTED,
                    description=f"SAGA started: {name} ({len(steps)} steps)",
                    tenant_id=tenant_id or "__anonymous__",
                    metadata={"saga_id": saga_id, "steps": len(steps)},
                )
            except Exception:
                pass
        return saga_id

    async def report_step_result(
        self,
        saga_id: str,
        step_name: str,
        success: bool,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> DistributedSagaState:
        """
        Report the result of a saga step execution.

        This is called by workers after executing a step. Based on
        the result, the coordinator either advances to the next step
        or initiates compensation.

        Args:
            saga_id: The saga being reported on.
            step_name: The step that completed/failed.
            success: Whether the step succeeded.
            result: Step result payload (on success).
            error: Error message (on failure).

        Returns:
            The saga's current state after processing the result.
        """
        # Get current saga state
        saga = await self._backend.get_saga(saga_id)
        if saga is None:
            logger.error(
                "SagaCoordinator: Saga %s not found", saga_id[:8],
            )
            return DistributedSagaState.FAILED

        if success:
            # Mark step as completed
            await self._backend.update_saga_step(
                saga_id, step_name, "COMPLETED", result=result,
            )

            # Update context with step result
            context = saga.get("context_data", {})
            if result:
                context[f"step_result_{step_name}"] = result

            # Find next step
            steps = saga.get("steps", [])
            current_idx = None
            for i, step in enumerate(steps):
                if step["step_name"] == step_name:
                    current_idx = i
                    break

            if current_idx is None:
                logger.error(
                    "SagaCoordinator: Step '%s' not found in saga %s",
                    step_name, saga_id[:8],
                )
                return DistributedSagaState.FAILED

            if current_idx + 1 < len(steps):
                # Dispatch next step
                next_step_data = steps[current_idx + 1]
                next_step = DistributedSagaStep(
                    name=next_step_data["step_name"],
                    action_task_type=next_step_data.get("action_task_type", ""),
                    compensation_task_type=next_step_data.get("compensation_task_type"),
                    timeout=next_step_data.get("timeout"),
                    priority=next_step_data.get("priority", TaskPriority.NORMAL),
                )
                await self._dispatch_step(
                    saga_id=saga_id,
                    step=next_step,
                    context=context,
                    tenant_id=saga.get("context_data", {}).get("tenant_id"),
                )
                return DistributedSagaState.RUNNING
            else:
                # All steps completed
                await self._backend.update_saga_status(
                    saga_id, "COMPLETED",
                )
                self._active_sagas.pop(saga_id, None)
                logger.info(
                    "SagaCoordinator: Saga %s completed successfully",
                    saga_id[:8],
                )
                # Phase 5: Audit event for saga completion
                if _AUDIT_AVAILABLE:
                    try:
                        audit = get_audit_logger()
                        audit.log_event(
                            event_type=AuditEventType.SAGA_COMPLETED,
                            description=f"SAGA completed: {saga.get('name', 'unknown')}",
                            tenant_id=saga.get("context_data", {}).get("tenant_id", "__anonymous__"),
                            metadata={"saga_id": saga_id},
                        )
                    except Exception:
                        pass
                return DistributedSagaState.COMPLETED

        else:
            # Step failed — initiate compensation
            await self._backend.update_saga_step(
                saga_id, step_name, "FAILED", error=error,
            )
            await self._backend.update_saga_status(
                saga_id, "COMPENSATING", error=error,
            )

            # Compensate all completed steps in reverse order
            await self._compensate(saga_id, saga, step_name)

            return DistributedSagaState.COMPENSATING

    # ----------------------------------------------------------
    #  COMPENSATION
    # ----------------------------------------------------------

    async def _compensate(
        self,
        saga_id: str,
        saga: Dict[str, Any],
        failed_step_name: str,
    ) -> None:
        """
        Compensate all completed steps in reverse order.

        Compensation failures are logged but do not stop the
        compensation process. All steps will have their compensation
        attempted.

        Args:
            saga_id: The saga being compensated.
            saga: The current saga state.
            failed_step_name: The step that triggered compensation.
        """
        steps = saga.get("steps", [])
        context = saga.get("context_data", {})

        # Find completed steps before the failed one
        completed_steps = []
        for step in steps:
            if step["step_name"] == failed_step_name:
                break
            if step.get("status") == "COMPLETED":
                completed_steps.append(step)

        compensation_errors: List[str] = []

        # Compensate in reverse order
        for step in reversed(completed_steps):
            comp_type = step.get("compensation_task_type")
            if comp_type is None:
                logger.warning(
                    "SagaCoordinator: Step '%s' has no compensation "
                    "(saga=%s)",
                    step["step_name"], saga_id[:8],
                )
                continue

            logger.info(
                "SagaCoordinator: Compensating step '%s' (saga=%s)",
                step["step_name"], saga_id[:8],
            )

            try:
                # Mark step as COMPENSATING
                await self._backend.update_saga_step(
                    saga_id, step["step_name"], "COMPENSATING",
                )

                # Dispatch compensation task
                await self._task_queue.enqueue(
                    TaskMessage(
                        queue_name=self._queue_name,
                        task_type=comp_type,
                        payload={
                            "saga_id": saga_id,
                            "step_name": step["step_name"],
                            "compensation": True,
                            "context": context,
                        },
                        priority=TaskPriority.HIGH,
                        tenant_id=context.get("tenant_id"),
                        correlation_id=context.get("correlation_id"),
                    )
                )

                # Mark step as COMPENSATED (optimistic — could wait for worker)
                await self._backend.update_saga_step(
                    saga_id, step["step_name"], "COMPENSATED",
                )

            except Exception as exc:
                error_msg = (
                    f"Compensation failed for step '{step['step_name']}': {exc}"
                )
                compensation_errors.append(error_msg)
                logger.error(
                    "SagaCoordinator: %s (saga=%s)", error_msg, saga_id[:8],
                )

        # Determine final status
        if compensation_errors:
            await self._backend.update_saga_status(
                saga_id, "FAILED", error="; ".join(compensation_errors),
            )
        else:
            await self._backend.update_saga_status(saga_id, "COMPENSATED")

        # Phase 5: Audit event for saga failure/compensation
        if _AUDIT_AVAILABLE:
            try:
                audit = get_audit_logger()
                event_type = AuditEventType.SAGA_FAILED if compensation_errors else AuditEventType.SAGA_COMPENSATED
                audit.log_event(
                    event_type=event_type,
                    description=f"SAGA {'failed' if compensation_errors else 'compensated'}: {saga.get('name', 'unknown')}",
                    severity=AuditSeverity.WARNING if not compensation_errors else AuditSeverity.CRITICAL,
                    tenant_id=saga.get("context_data", {}).get("tenant_id", "__anonymous__"),
                    metadata={"saga_id": saga_id, "compensation_errors": compensation_errors},
                )
            except Exception:
                pass

        self._active_sagas.pop(saga_id, None)

    # ----------------------------------------------------------
    #  STEP DISPATCH
    # ----------------------------------------------------------

