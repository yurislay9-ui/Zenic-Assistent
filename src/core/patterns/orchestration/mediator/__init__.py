"""
ZENIC-AGENTS - Mediator Pattern

Centralized request/response dispatcher for agent coordination.
Replaces direct agent-to-agent coupling with a mediator that routes
requests to the appropriate handler.

Features:
- Type-based request routing
- Pipeline behaviors (middleware) for cross-cutting concerns
- Sync and async dispatch
- Thread-safe handler registration and dispatch
- Dispatch logging for observability

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
No external dependencies beyond Python stdlib.
"""

import logging
import threading
from typing import Any, Dict, List

from ._types import (
    AsyncPipelineBehavior,
    PipelineBehavior,
    Request,
    RequestHandler,
    Response,
)
from ._sync_mixin import SyncDispatchMixin
from ._async_mixin import AsyncDispatchMixin

logger = logging.getLogger(__name__)

__all__ = [
    "Request",
    "Response",
    "RequestHandler",
    "Mediator",
]


class Mediator(SyncDispatchMixin, AsyncDispatchMixin):
    """
    Centralized request/response dispatcher with pipeline behaviors.

    Routes requests to registered handlers based on request_type.
    Supports pipeline behaviors (middleware) for cross-cutting concerns
    such as logging, validation, caching, and metrics.

    Usage::

        mediator = Mediator()

        class AnalyzeHandler(RequestHandler):
            def handle(self, request):
                return Response(success=True, data={"result": 42}, source="analyze")

        mediator.register("analyze", AnalyzeHandler())
        response = mediator.send(Request(request_type="analyze"))

    Pipeline Behaviors::

        def logging_pipeline(request, next_handler):
            logger.info("Handling %s", request.request_type)
            response = next_handler(request)
            logger.info("Result: %s", response.success)
            return response

        mediator.add_pipeline(logging_pipeline)

    Thread Safety:
        All operations are protected by threading.Lock.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, RequestHandler] = {}
        self._pipelines: List[PipelineBehavior] = []
        self._async_pipelines: List[AsyncPipelineBehavior] = []
        self._lock = threading.Lock()
        self._dispatch_count: int = 0
        self._error_count: int = 0

    # ----------------------------------------------------------
    #  HANDLER REGISTRATION
    # ----------------------------------------------------------

    def register(self, request_type: str, handler: RequestHandler) -> None:
        """
        Register a handler for a specific request type.

        Args:
            request_type: The request type this handler handles.
            handler: A RequestHandler instance.

        Raises:
            ValueError: If request_type is empty or handler is None.
        """
        if not request_type:
            raise ValueError("request_type must not be empty")
        if handler is None:
            raise ValueError("handler must not be None")

        with self._lock:
            self._handlers[request_type] = handler
            logger.info(
                "Mediator: Registered handler %s for request_type '%s'",
                type(handler).__name__, request_type,
            )

    # ----------------------------------------------------------
    #  PIPELINE BEHAVIORS
    # ----------------------------------------------------------

    def add_pipeline(self, behavior_fn: PipelineBehavior) -> None:
        """
        Add a pipeline behavior (middleware) that wraps handler execution.

        Pipeline behaviors are executed in the order they are added.
        Each behavior receives the request and a `next` callable that
        invokes the next behavior (or the actual handler).

        Args:
            behavior_fn: A callable with signature
                         (request, next_handler) -> Response
        """
        if behavior_fn is None:
            raise ValueError("behavior_fn must not be None")

        with self._lock:
            self._pipelines.append(behavior_fn)
            logger.debug(
                "Mediator: Added pipeline behavior '%s'",
                getattr(behavior_fn, '__name__', repr(behavior_fn)),
            )

    # ----------------------------------------------------------
    #  UTILITIES
    # ----------------------------------------------------------

    @property
    def stats(self) -> Dict[str, Any]:
        """
        Runtime statistics for monitoring and debugging.

        Returns:
            Dict with dispatch_count, errors_count, registered_handlers,
            registered_types, pipeline_count.
        """
        with self._lock:
            return {
                "dispatch_count": self._dispatch_count,
                "errors_count": self._error_count,
                "registered_handlers": len(self._handlers),
                "registered_types": list(self._handlers.keys()),
                "pipeline_count": len(self._pipelines),
            }

    def _error_count_inc(self) -> None:
        """Increment error counter in a thread-safe manner."""
        with self._lock:
            self._error_count += 1
