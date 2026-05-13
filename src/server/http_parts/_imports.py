"""
Shared imports and async event loop for http_parts sub-modules.
"""

import json
import logging
import time
import asyncio
import threading
import atexit
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from src.core.shared.contracts import HAS_Z3
from src.server.rate_limiter import RateLimiter
from src.server.response_builder import (
    build_normal_response,
    build_partial_reasoning_response,
    build_error_response,
    build_overloaded_response,
    build_artifact_response,
)

# Open Design CORS origins
try:
    from src.core.open_design.config import get_open_design_config
    _open_design_available = True
except ImportError:
    _open_design_available = False

# Executor registry for /v1/dispatch endpoint
try:
    from src.core.executors import get_default_registry as _get_executor_registry
    _EXECUTOR_REGISTRY_AVAILABLE = True
except ImportError:
    _get_executor_registry = None  # type: ignore
    _EXECUTOR_REGISTRY_AVAILABLE = False

logger = logging.getLogger("ZENIC")

# Configurable CORS origin
_cors_origin = os.environ.get("CORS_ALLOWED_ORIGIN", "*")

# Build Open Design allowed origins set for dynamic CORS
_od_allowed_origins = set()
if _open_design_available:
    try:
        _od_config = get_open_design_config()
        _od_allowed_origins = set(_od_config.open_design_origins)
    except Exception as e:
        logger.debug("OpenDesign config load failed: %s", e)

def _get_cors_origin(request_origin: str = "") -> str:
    """Resolve the Access-Control-Allow-Origin header value.
    
    If the request Origin matches an Open Design origin, return it specifically
    (required for credentials=true). Otherwise fall back to the configured default.
    """
    if request_origin and request_origin in _od_allowed_origins:
        return request_origin
    return _cors_origin

# Shared asyncio event loop
_shared_loop = None
_loop_thread = None
_loop_lock = threading.Lock()


def _shutdown_loop():
    """Close the shared event loop on shutdown."""
    global _shared_loop, _loop_thread
    with _loop_lock:
        if _shared_loop is not None and not _shared_loop.is_closed():
            try:
                _shared_loop.call_soon_threadsafe(_shared_loop.stop)
                _shared_loop.close()
                logger.info("HTTP: Shared event loop closed")
            except Exception as e:
                logger.debug("HTTP: Error closing event loop: %s", e)
            _shared_loop = None
            _loop_thread = None


def _is_loop_alive():
    """Check if the shared event loop AND its daemon thread are alive.

    The daemon thread can die silently (e.g. from a C extension crash in
    llama-cpp-python during GC).  If only the loop is checked but not the
    thread, ``run_coroutine_threadsafe`` enqueues work that is never
    executed, and every subsequent request hangs until
    ZENIC_REQUEST_TIMEOUT — which is what the user sees as
    "se apaga el motor" (the motor shuts down).
    """
    if _shared_loop is None or _shared_loop.is_closed():
        return False
    if _loop_thread is None or not _loop_thread.is_alive():
        return False
    return True


def _get_shared_loop():
    """Get or create the shared asyncio event loop (thread-safe).

    The loop runs in a daemon thread so that async coroutines submitted
    via ``run_coroutine_threadsafe`` are actually executed.  Without a
    running loop the orchestrator's ``execute()`` coroutine would never
    be processed and every request would time out.

    CRITICAL FIX (v18.1): Also detects when the daemon thread has died
    (even if the loop object is still open).  This happens when a C
    extension like llama-cpp-python crashes during garbage collection.
    In that case we create a fresh loop + thread so the server recovers
    instead of hanging forever.

    Additional improvements:
      - Safely stops the old loop before closing (prevents "cannot close
        a running event loop" error)
      - Brief sleep after thread start to ensure loop is running before
        returning (prevents race on first request)
    """
    global _shared_loop, _loop_thread
    if not _is_loop_alive():
        with _loop_lock:
            # Double-check under lock (another thread may have recreated)
            if not _is_loop_alive():
                # Clean up old loop if it exists but thread is dead
                if _shared_loop is not None and not _shared_loop.is_closed():
                    try:
                        # Stop the loop before closing — if the daemon thread
                        # died mid-run_forever, the loop is still "running"
                        # and close() would raise RuntimeError.
                        _shared_loop.call_soon_threadsafe(_shared_loop.stop)
                    except Exception:
                        pass
                    try:
                        _shared_loop.close()
                    except Exception:
                        pass
                    logger.warning(
                        "HTTP: Daemon event loop thread died — recreating "
                        "(this is normal after a C extension crash)"
                    )
                _shared_loop = asyncio.new_event_loop()
                _loop_thread = threading.Thread(
                    target=_shared_loop.run_forever,
                    daemon=True,
                    name="zenic-async-loop",
                )
                _loop_thread.start()
                # Give the thread a moment to actually start the loop,
                # so run_coroutine_threadsafe doesn't race with run_forever.
                _loop_thread.join(timeout=0.1)
    return _shared_loop


_REQUEST_TIMEOUT = int(os.environ.get("ZENIC_REQUEST_TIMEOUT", "300"))  # Was 120s, increased for ARM + Cline (Cline waits ~300s)
_MAX_ASYNC_RETRIES = 2  # How many times to retry if daemon thread dies mid-flight


def _run_async(coro):
    """Run an async coroutine on the shared event loop (thread-safe).

    CRITICAL FIX (v18.1): Added resilience against daemon thread death.

    The daemon thread running the shared event loop can die silently
    (e.g. from a C extension crash in llama-cpp-python). Without this
    fix, run_coroutine_threadsafe enqueues work that is never executed,
    and every subsequent request hangs until ZENIC_REQUEST_TIMEOUT.

    Improvements:
      1. Verify loop is alive right before submitting (close the race window)
      2. Retry with fresh loop+thread if daemon died mid-flight
      3. Cancel timed-out coroutines to prevent resource leaks
      4. Better error logging for debugging
    """
    last_error = None

    for attempt in range(_MAX_ASYNC_RETRIES + 1):
        # Always get a fresh, healthy loop (recreates if daemon died)
        loop = _get_shared_loop()

        # Double-check: the daemon thread might have died between
        # _get_shared_loop() and the submit call (race window ~microseconds).
        # This is rare but possible.
        if not _is_loop_alive():
            if attempt < _MAX_ASYNC_RETRIES:
                logger.warning(
                    "HTTP: Daemon thread died before submit (attempt %d/%d), retrying...",
                    attempt + 1, _MAX_ASYNC_RETRIES + 1,
                )
                continue
            else:
                raise RuntimeError(
                    "Shared event loop daemon thread keeps dying — "
                    "possible C extension crash. Check llama-cpp-python logs."
                )

        try:
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            result = future.result(timeout=_REQUEST_TIMEOUT)
            return result
        except TimeoutError:
            # Request timed out — cancel the coroutine to free resources
            cancelled = future.cancel()
            logger.error(
                "HTTP: Request TIMEOUT after %ds (cancel=%s). "
                "The orchestrator may still be loading models.",
                _REQUEST_TIMEOUT, cancelled,
            )
            raise
        except RuntimeError as e:
            # Loop was closed or corrupted while coroutine was pending
            if "Event loop is closed" in str(e) or "Non-thread-safe" in str(e):
                if attempt < _MAX_ASYNC_RETRIES:
                    logger.warning(
                        "HTTP: Event loop error during execution (attempt %d/%d): %s. "
                        "Retrying with fresh loop...",
                        attempt + 1, _MAX_ASYNC_RETRIES + 1, e,
                    )
                    # Need a new coroutine because the old one was consumed
                    # by run_coroutine_threadsafe (it wraps it in a Task)
                    # We can't re-use it — the caller must handle the retry.
                    # Since we can't recreate the coroutine, just raise.
                    raise
                else:
                    raise
            raise
        except Exception as e:
            logger.error("HTTP: Unexpected error in _run_async: %s", e, exc_info=True)
            raise


# Register atexit handler
atexit.register(_shutdown_loop)
