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

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ============================================================
#  MIDDLEWARE CONTEXT
# ============================================================



class _MiddlewareContext:
    """
    Context object passed through the middleware chain.

    Attributes:
        action_name: Name of the action being executed.
        args: Positional arguments to the function.
        kwargs: Keyword arguments to the function.
        result: Return value of the function (populated after execution).
        error: Exception raised by the function (if any).
        metadata: Arbitrary metadata dict.
        start_time: Monotonic timestamp when execution started.
        end_time: Monotonic timestamp when execution ended.
    """

    __slots__ = (
        "action_name", "args", "kwargs", "result", "error",
        "metadata", "start_time", "end_time",
    )

    def __init__(
        self,
        action_name: str,
        args: tuple = (),
        kwargs: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        self.action_name = action_name
        self.args = args
        self.kwargs = kwargs or {}
        self.result: Any = None
        self.error: Optional[Exception] = None
        self.metadata: Dict[str, Any] = dict(metadata or {})
        self.start_time: float = 0.0
        self.end_time: float = 0.0

    @property
    def duration(self) -> float:
        """Duration of the call in seconds, or 0.0 if not yet complete."""
        if self.end_time > 0 and self.start_time > 0:
            return self.end_time - self.start_time
        return 0.0


# ============================================================
#  SIDECAR
# ============================================================
