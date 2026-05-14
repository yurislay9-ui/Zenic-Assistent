"""DistributedWorker - Async helpers and observability wiring."""

import asyncio
import threading

# Phase 5: Observability wiring
try:
    from src.core.observability.metrics import get_metrics_collector
    _METRICS_AVAILABLE = True
except ImportError:
    get_metrics_collector = None  # type: ignore
    _METRICS_AVAILABLE = False


# ============================================================
#  THREAD-LOCAL EVENT LOOP HELPER (H-07 fix)
# ============================================================

_local = threading.local()


def _get_thread_loop() -> asyncio.AbstractEventLoop:
    """Get or create a persistent event loop for the current thread.

    PERFORMANCE (H-07 fix): Instead of creating a new asyncio event loop
    for every async operation (which leaks resources and adds overhead),
    each thread reuses a single loop for its entire lifetime.
    """
    loop = getattr(_local, "event_loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _local.event_loop = loop
    return loop


def _run_async(coro):
    """Run an async coroutine on the current thread's persistent event loop."""
    loop = _get_thread_loop()
    return loop.run_until_complete(coro)
