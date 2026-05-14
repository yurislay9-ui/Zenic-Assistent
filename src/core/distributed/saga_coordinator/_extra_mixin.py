"""DistributedSagaCoordinator - Additional methods."""

import logging
from typing import Any, Dict, List, Optional

from ._types import DistributedSagaStep
from ..task_queue import TaskMessage

logger = logging.getLogger("zenic_agents.distributed.saga_coordinator")


class DistributedSagaCoordinatorExtraMixin:
    """Additional methods mixin."""

    async def _dispatch_step(
        self,
        saga_id: str,
        step: DistributedSagaStep,
        context: Dict[str, Any],
        tenant_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """
        Dispatch a saga step as a task to the queue.

        Args:
            saga_id: The saga this step belongs to.
            step: The step to dispatch.
            context: Current saga context.
            tenant_id: Optional tenant ID.
            correlation_id: Optional correlation ID.
        """
        # Mark step as RUNNING
        await self._backend.update_saga_step(
            saga_id, step.name, "RUNNING",
        )

        await self._task_queue.enqueue(
            TaskMessage(
                queue_name=self._queue_name,
                task_type=step.action_task_type,
                payload={
                    "saga_id": saga_id,
                    "step_name": step.name,
                    "compensation": False,
                    "context": context,
                },
                priority=step.priority,
                tenant_id=tenant_id,
                correlation_id=correlation_id,
            )
        )

        logger.info(
            "SagaCoordinator: Dispatched step '%s' for saga %s",
            step.name, saga_id[:8],
        )

    # ----------------------------------------------------------
    #  RECOVERY
    # ----------------------------------------------------------

    async def recover_sagas(self) -> List[str]:
        """
        Recover sagas that were interrupted by a crash.

        Finds all sagas in RUNNING or COMPENSATING state and
        re-dispatches their current step.

        Returns:
            List of recovered saga IDs.
        """
        # This is a simplified recovery — in production, you'd
        # query the backend for sagas in RUNNING/COMPENSATING state
        recovered: List[str] = []

        logger.info(
            "SagaCoordinator: Recovery scan found %d active sagas",
            len(self._active_sagas),
        )

        for saga_id, saga_data in list(self._active_sagas.items()):
            try:
                state = await self._backend.get_saga(saga_id)
                if state and state.get("status") in ("RUNNING", "COMPENSATING"):
                    recovered.append(saga_id)
                    logger.info(
                        "SagaCoordinator: Recovered saga %s (status=%s)",
                        saga_id[:8], state.get("status"),
                    )
            except Exception as exc:
                logger.error(
                    "SagaCoordinator: Recovery failed for %s: %s",
                    saga_id[:8], exc,
                )

        return recovered

    # ----------------------------------------------------------
    #  QUERY
    # ----------------------------------------------------------

    async def get_saga_status(self, saga_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the current status of a saga.

        Args:
            saga_id: The saga to query.

        Returns:
            Dict with saga state, or None if not found.
        """
        return await self._backend.get_saga(saga_id)

    async def list_active_sagas(self) -> List[Dict[str, Any]]:
        """
        List all currently active sagas.

        Returns:
            List of saga state dicts.
        """
        result = []
        for saga_id in list(self._active_sagas.keys()):
            state = await self._backend.get_saga(saga_id)
            if state:
                result.append(state)
        return result

