"""
ZENIC-AGENTS - Mediator Pattern: Sync Dispatch Mixin
"""

import logging
import threading
from typing import Any, Callable, Dict, List

from ._types import PipelineBehavior, Request, Response

logger = logging.getLogger(__name__)


def _wrap_pipeline(
    next_fn: Callable[[Request], Response],
    pipeline: PipelineBehavior,
) -> Callable[[Request], Response]:
    """
    Wrap a handler callable with a pipeline behavior.

    Creates a closure that invokes the pipeline with the request
    and the next callable.
    """
    def _wrapped(request: Request) -> Response:
        return pipeline(request, next_fn)
    return _wrapped


class SyncDispatchMixin:
    """Mixin providing synchronous dispatch for the Mediator."""

    def send(self: Any, request: Request) -> Response:
        """
        Synchronously dispatch a request to its registered handler.

        Pipeline behaviors are applied in order, wrapping the actual
        handler execution. If no handler is registered for the
        request_type, returns an error Response.
        """
        with self._lock:
            self._dispatch_count += 1
            handler = self._handlers.get(request.request_type)
            pipelines = list(self._pipelines)

        # Log dispatch
        logger.info(
            "Mediator: Dispatching request_type='%s' (pipelines=%d)",
            request.request_type, len(pipelines),
        )

        if handler is None:
            error_msg = (
                f"No handler registered for request_type '{request.request_type}'"
            )
            logger.warning("Mediator: %s", error_msg)
            self._error_count_inc()
            return Response(
                success=False,
                error=error_msg,
                source="Mediator",
            )

        # Build the handler chain
        def _build_chain(
            handler_fn: Callable[[Request], Response],
            pipelines: List[PipelineBehavior],
        ) -> Callable[[Request], Response]:
            chain = handler_fn
            for pipeline in reversed(pipelines):
                chain = _wrap_pipeline(chain, pipeline)
            return chain

        try:
            chain = _build_chain(handler.handle, pipelines)
            response = chain(request)
            return response
        except Exception as exc:
            self._error_count_inc()
            logger.error(
                "Mediator: Handler failed for request_type '%s': %s",
                request.request_type, exc,
                exc_info=True,
            )
            return Response(
                success=False,
                error=str(exc),
                source=type(handler).__name__,
            )
