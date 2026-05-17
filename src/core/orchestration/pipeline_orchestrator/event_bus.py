"""
Event Bus — Event pub/sub system for pipeline orchestration.

Provides a lightweight, thread-safe event bus specifically designed
for pipeline orchestration events, supporting wildcard subscriptions,
error isolation, and both sync and async publish modes.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
No external dependencies beyond Python stdlib.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "PipelineEvent",
    "PipelineEventHandler",
    "EventBus",
]


# ──────────────────────────────────────────────────────────────
#  DATA CONTRACTS
# ──────────────────────────────────────────────────────────────

class PipelineEventType(str, Enum):
    """Types of pipeline events."""
    PIPELINE_CREATED = "pipeline.created"
    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"
    PIPELINE_CANCELLED = "pipeline.cancelled"
    STEP_STARTED = "step.started"
    STEP_COMPLETED = "step.completed"
    STEP_FAILED = "step.failed"
    STEP_SKIPPED = "step.skipped"
    STEP_RETRYING = "step.retrying"
    ROLLBACK_STARTED = "rollback.started"
    ROLLBACK_COMPLETED = "rollback.completed"
    ROLLBACK_FAILED = "rollback.failed"
    PROGRESS_UPDATED = "progress.updated"
    COMPLIANCE_CHECK = "compliance.check"
    COMPLIANCE_VIOLATION = "compliance.violation"
    CUSTOM = "custom"


@dataclass
class PipelineEvent:
    """
    Immutable event payload for pipeline orchestration.

    Attributes:
        event_type: Type of event (for routing).
        pipeline_id: The pipeline this event relates to.
        step_id: The step this event relates to (optional).
        data: Arbitrary event payload.
        timestamp: Unix timestamp of event creation.
        source: Origin identifier for tracing.
        correlation_id: Correlation ID for distributed tracing.
    """
    event_type: str
    pipeline_id: str = ""
    step_id: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    source: Optional[str] = None
    correlation_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.event_type:
            raise ValueError("PipelineEvent event_type must not be empty")


class PipelineEventHandler(ABC):
    """
    Abstract base class for pipeline event handlers.

    Subclasses must implement:
    - handle(event): Process the event
    - can_handle(event_type): Declare which events this handler accepts
    """

    @abstractmethod
    def handle(self, event: PipelineEvent) -> Any:
        """
        Process the given pipeline event.

        Args:
            event: The PipelineEvent instance to process.
        """
        ...

    @abstractmethod
    def can_handle(self, event_type: str) -> bool:
        """
        Determine if this handler is interested in the given event type.

        Args:
            event_type: The event type to check.

        Returns:
            True if this handler should receive events of this type.
        """
        ...


# ──────────────────────────────────────────────────────────────
#  EVENT BUS
# ──────────────────────────────────────────────────────────────

class EventBus:
    """
    Thread-safe publish/subscribe event bus for pipeline orchestration.

    Supports:
    - Wildcard subscription ("*" receives all events)
    - Error isolation: one handler failure does not affect others
    - Sync and async publish modes
    - Result collection for request/response-style usage
    - Pipeline-specific event routing

    Usage::

        bus = EventBus()

        class StepHandler(PipelineEventHandler):
            def handle(self, event):
                print(f"Step {event.step_id}: {event.event_type}")
            def can_handle(self, event_type):
                return event_type.startswith("step.")

        bus.subscribe("step.", StepHandler())
        bus.publish(PipelineEvent(
            event_type="step.completed",
            pipeline_id="pipe-1",
            step_id="extract",
        ))

    Thread Safety:
        All mutating operations are protected by a threading.Lock.
    """

    WILDCARD = "*"

    def __init__(self) -> None:
        self._handlers: Dict[str, List[PipelineEventHandler]] = defaultdict(list)
        self._lock = threading.Lock()
        self._events_published: int = 0
        self._errors_count: int = 0

    # ── Subscription Management ──────────────────────────────

    def subscribe(self, event_type: str, handler: PipelineEventHandler) -> None:
        """
        Register a handler for a specific event type.

        Args:
            event_type: The event type to listen for. Use "*" for all events.
            handler: A PipelineEventHandler instance.

        Raises:
            ValueError: If event_type is empty or handler is None.
        """
        if not event_type:
            raise ValueError("event_type must not be empty")
        if handler is None:
            raise ValueError("handler must not be None")

        with self._lock:
            if handler not in self._handlers[event_type]:
                self._handlers[event_type].append(handler)
                logger.debug(
                    "EventBus: Handler %s subscribed to '%s'",
                    type(handler).__name__, event_type,
                )

    def subscribe_fn(
        self,
        event_type: str,
        handler_fn: Callable[[PipelineEvent], None],
    ) -> None:
        """
        Subscribe a plain function as a handler.

        Args:
            event_type: The event type to listen for.
            handler_fn: A callable that accepts a PipelineEvent.
        """
        fn_handler = _FunctionHandler(handler_fn)
        self.subscribe(event_type, fn_handler)

    def unsubscribe(self, event_type: str, handler: PipelineEventHandler) -> None:
        """
        Remove a handler from a specific event type.

        Args:
            event_type: The event type the handler was subscribed to.
            handler: The handler instance to remove.
        """
        with self._lock:
            handlers = self._handlers.get(event_type)
            if handlers and handler in handlers:
                handlers.remove(handler)
                if not handlers:
                    del self._handlers[event_type]

    # ── Publish (Sync) ───────────────────────────────────────

    def publish(self, event: PipelineEvent) -> None:
        """
        Synchronously publish an event to all matching subscribers.

        Wildcard subscribers always receive the event. Error isolation
        ensures one handler failure does not affect others.

        Args:
            event: The PipelineEvent to publish.
        """
        with self._lock:
            self._events_published += 1
            specific = list(self._handlers.get(event.event_type, []))
            wildcard = list(self._handlers.get(self.WILDCARD, []))
            target_handlers = specific + wildcard

        for handler in target_handlers:
            try:
                handler.handle(event)
            except Exception as exc:
                self._error_count_inc()
                logger.error(
                    "EventBus: Handler %s failed on event '%s': %s",
                    type(handler).__name__, event.event_type, exc,
                )

    # ── Publish (Async) ──────────────────────────────────────

    async def publish_async(self, event: PipelineEvent) -> None:
        """
        Asynchronously publish an event to all matching subscribers.

        Args:
            event: The PipelineEvent to publish.
        """
        with self._lock:
            self._events_published += 1
            specific = list(self._handlers.get(event.event_type, []))
            wildcard = list(self._handlers.get(self.WILDCARD, []))
            target_handlers = specific + wildcard

        async def _safe_call(handler: PipelineEventHandler, evt: PipelineEvent) -> None:
            try:
                result = handler.handle(evt)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                self._error_count_inc()
                logger.error(
                    "EventBus[async]: Handler %s failed: %s",
                    type(handler).__name__, exc,
                )

        await asyncio.gather(
            *[_safe_call(h, event) for h in target_handlers],
            return_exceptions=False,
        )

    # ── Publish and Collect ──────────────────────────────────

    def publish_and_collect(self, event: PipelineEvent) -> List[Any]:
        """
        Publish an event and collect return values from handlers.

        Args:
            event: The PipelineEvent to publish.

        Returns:
            List of values returned by handlers.
        """
        with self._lock:
            self._events_published += 1
            specific = list(self._handlers.get(event.event_type, []))
            wildcard = list(self._handlers.get(self.WILDCARD, []))
            target_handlers = specific + wildcard

        results: List[Any] = []
        for handler in target_handlers:
            try:
                result = handler.handle(event)
                results.append(result)
            except Exception as exc:
                self._error_count_inc()
                logger.error(
                    "EventBus[collect]: Handler %s failed: %s",
                    type(handler).__name__, exc,
                )
        return results

    # ── Utilities ────────────────────────────────────────────

    def clear(self) -> None:
        """Remove all handlers."""
        with self._lock:
            self._handlers.clear()

    @property
    def stats(self) -> Dict[str, Any]:
        """Runtime statistics."""
        with self._lock:
            total_handlers = sum(len(h) for h in self._handlers.values())
            return {
                "events_published": self._events_published,
                "handlers_count": total_handlers,
                "errors_count": self._errors_count,
                "event_types": list(self._handlers.keys()),
            }

    def _error_count_inc(self) -> None:
        """Increment error counter thread-safely."""
        with self._lock:
            self._errors_count += 1


# ──────────────────────────────────────────────────────────────
#  INTERNAL: Function Handler Adapter
# ──────────────────────────────────────────────────────────────

class _FunctionHandler(PipelineEventHandler):
    """Adapts a plain function to the PipelineEventHandler interface."""

    def __init__(self, fn: Callable[[PipelineEvent], None]) -> None:
        self._fn = fn

    def handle(self, event: PipelineEvent) -> Any:
        self._fn(event)

    def can_handle(self, event_type: str) -> bool:
        return True  # subscribed explicitly, always accept
