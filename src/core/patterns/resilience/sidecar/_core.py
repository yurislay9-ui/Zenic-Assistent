"""
ZENIC-AGENTS - Sidecar Pattern v16

Cross-cutting concern observer for timing, logging, metrics, and
middleware chains. Designed for Android/Termux (500MB RAM) — stdlib only.

The Sidecar acts as a companion to any function, adding observability
and middleware hooks without modifying the function's core logic.

Usage::

    sidecar = Sidecar("user-service")

    @sidecar.wrap
    def fetch_user(user_id):
        return db.query(user_id)

    # Middleware that can observe/transform calls
    sidecar.add_middleware(lambda ctx: ctx)  # pass-through
"""

import asyncio
import functools
import logging
import threading
import time
from collections import deque
from contextlib import contextmanager
from typing import Any, Callable, Deque, Dict, List, Optional

from ._types import _MiddlewareContext
logger = logging.getLogger("core.patterns.resilience.sidecar._core")

class Sidecar:
    """
    Sidecar for cross-cutting concerns: timing, logging, metrics,
    and middleware chains.

    Parameters:
        name: Human-readable identifier for this sidecar.
        max_history: Maximum number of recent action records to keep.
    """

    def __init__(self, name: str, max_history: int = 100) -> None:
        if max_history < 1:
            raise ValueError("max_history must be >= 1")

        self._name = name
        self._max_history = max_history

        # Metrics
        self._call_count = 0
        self._error_count = 0
        self._total_duration = 0.0
        self._last_error: Optional[Exception] = None
        self._last_error_time: Optional[float] = None

        # Per-action metrics
        self._action_metrics: Dict[str, Dict[str, Any]] = {}

        # Middleware chain
        self._middlewares: List[Callable[[_MiddlewareContext], _MiddlewareContext]] = []

        # Recent history for debugging
        self._history: Deque[_MiddlewareContext] = deque(maxlen=max_history)

        self._lock = threading.Lock()

    # ----------------------------------------------------------
    #  Properties
    # ----------------------------------------------------------

    @property
    def name(self) -> str:
        """Identifier for this sidecar."""
        return self._name

    @property
    def stats(self) -> Dict[str, Any]:
        """Snapshot of sidecar statistics."""
        with self._lock:
            avg_duration = (
                self._total_duration / self._call_count
                if self._call_count > 0
                else 0.0
            )
            return {
                "name": self._name,
                "call_count": self._call_count,
                "error_count": self._error_count,
                "success_count": self._call_count - self._error_count,
                "total_duration": self._total_duration,
                "average_duration": avg_duration,
                "last_error": str(self._last_error) if self._last_error else None,
                "last_error_time": self._last_error_time,
                "action_metrics": dict(self._action_metrics),
                "middleware_count": len(self._middlewares),
                "history_size": len(self._history),
            }

    # ----------------------------------------------------------
    #  Middleware
    # ----------------------------------------------------------

    def add_middleware(
        self,
        middleware_fn: Callable[[_MiddlewareContext], _MiddlewareContext],
    ) -> None:
        """
        Add a middleware function to the processing chain.

        Middleware receives a ``_MiddlewareContext`` and must return it
        (potentially modified). Middlewares are executed in the order
        they are added, before the actual function call for
        pre-processing, and after for post-processing.

        Args:
            middleware_fn: A callable that receives and returns a
                _MiddlewareContext.
        """
        with self._lock:
            self._middlewares.append(middleware_fn)

    def _run_middlewares(self, ctx: _MiddlewareContext) -> _MiddlewareContext:
        """Execute all middlewares in order."""
        for mw in self._middlewares:
            try:
                ctx = mw(ctx)
            except Exception as mw_err:
                logger.warning(
                    "Sidecar '%s': middleware error in action '%s': %s",
                    self._name, ctx.action_name, mw_err,
                )
        return ctx

    # ----------------------------------------------------------
    #  Hooks — before / after / on_error
    # ----------------------------------------------------------

    @contextmanager
    def before(self, action_name: str, metadata: Optional[Dict[str, Any]] = None):  # noqa: ANN201
        """
        Context manager for before-hooks. Starts timing and runs
        middlewares in pre-processing phase.

        Usage::

            with sidecar.before("process-order", {"order_id": 42}) as ctx:
                result = do_work()
                ctx.result = result
            # after-hook runs automatically on context exit
        """
        ctx = _MiddlewareContext(
            action_name=action_name,
            metadata=metadata,
        )
        ctx.start_time = time.monotonic()

        # Pre-process through middlewares
        ctx = self._run_middlewares(ctx)

        logger.debug(
            "Sidecar '%s': before '%s' (metadata=%s)",
            self._name, action_name, ctx.metadata,
        )

        try:
            yield ctx
        except Exception as exc:
            ctx.error = exc
            self._record_error(action_name, exc, ctx.metadata)
            raise
        else:
            self._record_success(action_name, ctx)
        finally:
            ctx.end_time = time.monotonic()
            with self._lock:
                self._history.append(ctx)

    def after(
        self,
        action_name: str,
        result: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record a successful after-hook for *action_name*.

        This is a convenience method for manual hook registration
        when the context manager is not used.
        """
        ctx = _MiddlewareContext(
            action_name=action_name,
            metadata=metadata,
        )
        ctx.result = result
        ctx.start_time = time.monotonic()
        ctx.end_time = time.monotonic()
        self._record_success(action_name, ctx)
        with self._lock:
            self._history.append(ctx)

    def on_error(
        self,
        action_name: str,
        error: Exception,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record an error-hook for *action_name*.

        This is a convenience method for manual hook registration.
        """
        ctx = _MiddlewareContext(
            action_name=action_name,
            metadata=metadata,
        )
        ctx.error = error
        ctx.start_time = time.monotonic()
        ctx.end_time = time.monotonic()
        self._record_error(action_name, error, metadata)
        with self._lock:
            self._history.append(ctx)

    # ----------------------------------------------------------
    #  Decorators — wrap / wrap_async
    # ----------------------------------------------------------

    def wrap(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """
        Decorator that adds timing, logging, and metrics to a
        synchronous function.
        """
        action_name = getattr(func, "__name__", repr(func))

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with self.before(action_name) as ctx:
                ctx.args = args
                ctx.kwargs = kwargs
                result = func(*args, **kwargs)
                ctx.result = result
            return result

        return wrapper

    def wrap_async(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """
        Decorator that adds timing, logging, and metrics to an
        asynchronous function.
        """
        action_name = getattr(func, "__name__", repr(func))

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = _MiddlewareContext(
                action_name=action_name,
                args=args,
                kwargs=kwargs,
            )
            ctx.start_time = time.monotonic()
            ctx = self._run_middlewares(ctx)

            logger.debug(
                "Sidecar '%s': before async '%s'",
                self._name, action_name,
            )

            try:
                result = await func(*args, **kwargs)
            except Exception as exc:
                ctx.error = exc
                ctx.end_time = time.monotonic()
                self._record_error(action_name, exc, ctx.metadata)
                with self._lock:
                    self._history.append(ctx)
                raise
            else:
                ctx.result = result
                ctx.end_time = time.monotonic()
                self._record_success(action_name, ctx)
                with self._lock:
                    self._history.append(ctx)
                return result

        return wrapper

    # ----------------------------------------------------------
    #  Internal recording
    # ----------------------------------------------------------

    def _record_success(
        self, action_name: str, ctx: _MiddlewareContext
    ) -> None:
        """Record a successful call."""
        duration = ctx.duration
        with self._lock:
            self._call_count += 1
            self._total_duration += duration

            # Per-action metrics
            if action_name not in self._action_metrics:
                self._action_metrics[action_name] = {
                    "call_count": 0,
                    "error_count": 0,
                    "total_duration": 0.0,
                }
            metrics = self._action_metrics[action_name]
            metrics["call_count"] += 1
            metrics["total_duration"] += duration

        logger.debug(
            "Sidecar '%s': after '%s' (duration=%.4fs)",
            self._name, action_name, duration,
        )

    def _record_error(
        self,
        action_name: str,
        error: Exception,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a failed call."""
        with self._lock:
            self._call_count += 1
            self._error_count += 1
            self._last_error = error
            self._last_error_time = time.monotonic()

            # Per-action metrics
            if action_name not in self._action_metrics:
                self._action_metrics[action_name] = {
                    "call_count": 0,
                    "error_count": 0,
                    "total_duration": 0.0,
                }
            metrics = self._action_metrics[action_name]
            metrics["call_count"] += 1
            metrics["error_count"] += 1

        logger.warning(
            "Sidecar '%s': error in '%s': %s (metadata=%s)",
            self._name, action_name, error, metadata,
        )

    # ----------------------------------------------------------
    #  Dunder helpers
    # ----------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"Sidecar(name={self._name!r}, "
            f"calls={self._call_count}, "
            f"errors={self._error_count})"
        )


# ============================================================
#  CONVENIENCE DECORATOR
# ============================================================

def sidecar_decorator(sidecar_instance: Sidecar) -> Callable[..., Any]:
    """
    Convenience decorator factory that wraps a function with the
    given sidecar instance.

    Usage::

        svc_sidecar = Sidecar("user-service")

        @sidecar_decorator(svc_sidecar)
        def fetch_user(uid):
            ...
    """
    return sidecar_instance.wrap
