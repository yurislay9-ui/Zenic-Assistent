"""
ZENIC-AGENTS - Mediator Pattern: Async Dispatch Mixin
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, List

from ._types import AsyncPipelineBehavior, PipelineBehavior, Request, Response

logger = logging.getLogger(__name__)


class AsyncDispatchMixin:
    """Mixin providing asynchronous dispatch for the Mediator."""

    async def send_async(self: Any, request: Request) -> Response:
        """
        Asynchronously dispatch a request to its registered handler.

        Supports async handlers and async pipeline behaviors.
        Sync handlers are automatically wrapped to run in the
        default executor.
        """
        with self._lock:
            self._dispatch_count += 1
            handler = self._handlers.get(request.request_type)
            pipelines = list(self._pipelines)
            async_pipelines = list(self._async_pipelines)

        logger.info(
            "Mediator[async]: Dispatching request_type='%s' "
            "(sync_pipelines=%d, async_pipelines=%d)",
            request.request_type, len(pipelines), len(async_pipelines),
        )

        if handler is None:
            error_msg = (
                f"No handler registered for request_type '{request.request_type}'"
            )
            logger.warning("Mediator[async]: %s", error_msg)
            self._error_count_inc()
            return Response(
                success=False,
                error=error_msg,
                source="Mediator",
            )

        try:
            # Wrap sync handler as async
            async def _async_handle(req: Request) -> Response:
                result = handler.handle(req)
                if asyncio.iscoroutine(result):
                    result = await result
                return result

            # Build async chain with async pipelines
            chain: Callable[[Request], Awaitable[Response]] = _async_handle

            # Apply async pipelines (reverse order for nesting)
            for pipeline in reversed(async_pipelines):
                prev_chain = chain

                async def _make_async_step(
                    req: Request,
                    _pipeline: AsyncPipelineBehavior = pipeline,
                    _next: Callable[[Request], Awaitable[Response]] = prev_chain,
                ) -> Response:
                    return await _pipeline(req, _next)

                chain = _make_async_step  # type: ignore[assignment]

            # Apply sync pipelines as async wrappers (reverse order)
            for pipeline in reversed(pipelines):
                prev_chain = chain

                async def _make_sync_step(
                    req: Request,
                    _pipeline: PipelineBehavior = pipeline,
                    _next: Callable[[Request], Awaitable[Response]] = prev_chain,
                ) -> Response:
                    # Wrap the async next in a sync-compatible way
                    def _sync_next(r: Request) -> Response:
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor(
                            max_workers=1
                        ) as pool:
                            future = pool.submit(asyncio.run, _next(r))
                            return future.result()

                    return _pipeline(req, _sync_next)

                chain = _make_sync_step  # type: ignore[assignment]

            response = await chain(request)
            return response

        except Exception as exc:
            self._error_count_inc()
            logger.error(
                "Mediator[async]: Handler failed for request_type '%s': %s",
                request.request_type, exc,
                exc_info=True,
            )
            return Response(
                success=False,
                error=str(exc),
                source=type(handler).__name__,
            )
