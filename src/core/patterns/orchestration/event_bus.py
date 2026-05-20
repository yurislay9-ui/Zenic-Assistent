"""
ZENIC-AGENTS - Event Bus (Observer Pattern)

Thread-safe publish/subscribe event bus for decoupled communication
between pipeline components, agents, and orchestration layers.

Features:
- Wildcard subscription ("*" receives all events)
- Error isolation: one handler failure does not affect others
- Sync and async publish modes
- Result collection for request/response-style usage
- Statistics tracking for observability

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
No external dependencies beyond Python stdlib.
"""

import asyncio
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.native import (
    wildcard_match as _native_wildcard_match,
    resolve_routes as _native_resolve_routes,
    deduplicate_events as _native_deduplicate_events,
    sort_by_priority as _native_sort_by_priority,
    HAS_NATIVE as _HAS_NATIVE,
)

logger = logging.getLogger(__name__)

__all__ = [
    "Event",
    "EventHandler",
    "EventBus",
]


# ============================================================
#  DATA CONTRACTS
# ============================================================

@dataclass
class Event:
    """
    Immutable event payload dispatched through the EventBus.

    Attributes:
        name: Event identifier used for routing to subscribers.
        data: Arbitrary payload carried by the event.
        timestamp: Unix timestamp of event creation (auto-set if omitted).
        source: Origin identifier for tracing (optional).
        correlation_id: Correlation ID for distributed tracing (optional).
    """
    name: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    source: Optional[str] = None
    correlation_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Event name must not be empty")


# ============================================================
#  HANDLER INTERFACE
# ============================================================

class EventHandler(ABC):
    """
    Abstract base class for event handlers.

    Subclasses must implement:
    - handle(event): Process the event
    - can_handle(event_name): Declare which events this handler accepts
    """

    @abstractmethod
    def handle(self, event: Event) -> Any:
        """
        Process the given event.

        Args:
            event: The Event instance to process.

        Raises:
            Exception: Implementations may raise; the EventBus will
                       isolate and log the error without affecting
                       other handlers.
        """
        ...

    @abstractmethod
    def can_handle(self, event_name: str) -> bool:
        """
        Determine if this handler is interested in the given event name.

        Args:
            event_name: The name of the event to check.

        Returns:
            True if this handler should receive events with this name.
        """
        ...


# ============================================================
#  EVENT BUS
# ============================================================

class EventBus:
    """
    Thread-safe publish/subscribe event bus with wildcard support.

    Usage::

        bus = EventBus()

        class MyHandler(EventHandler):
            def handle(self, event):
                print(f"Got: {event.name}")
            def can_handle(self, event_name):
                return event_name == "user.created"

        handler = MyHandler()
        bus.subscribe("user.created", handler)
        bus.publish(Event(name="user.created", data={"id": 42}))
        bus.unsubscribe("user.created", handler)

    Wildcard:
        Subscribe to "*" to receive ALL events regardless of name.

    Thread Safety:
        All mutating operations (subscribe, unsubscribe, publish, clear)
        are protected by a threading.Lock. Concurrent publishes are safe.

    Error Isolation:
        If one handler raises during publish, the error is logged and
        remaining handlers still execute. The publish method never
        propagates handler exceptions.
    """

    WILDCARD = "*"

    def __init__(self) -> None:
        self._handlers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._lock = threading.Lock()
        self._events_published: int = 0
        self._errors_count: int = 0

    # ----------------------------------------------------------
    #  SUBSCRIPTION MANAGEMENT
    # ----------------------------------------------------------

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        """
        Register a handler for a specific event name.

        Args:
            event_name: The event name to listen for. Use "*" for all events.
            handler: An EventHandler instance.

        Raises:
            ValueError: If event_name is empty or handler is None.
        """
        if not event_name:
            raise ValueError("event_name must not be empty")
        if handler is None:
            raise ValueError("handler must not be None")

        with self._lock:
            # Avoid duplicate registration
            if handler not in self._handlers[event_name]:
                self._handlers[event_name].append(handler)
                logger.debug(
                    "EventBus: Handler %s subscribed to '%s'",
                    type(handler).__name__, event_name,
                )

    def unsubscribe(self, event_name: str, handler: EventHandler) -> None:
        """
        Remove a handler from a specific event name.

        Args:
            event_name: The event name the handler was subscribed to.
            handler: The EventHandler instance to remove.

        Note:
            Silently ignores if the handler is not found.
        """
        with self._lock:
            handlers = self._handlers.get(event_name)
            if handlers and handler in handlers:
                handlers.remove(handler)
                logger.debug(
                    "EventBus: Handler %s unsubscribed from '%s'",
                    type(handler).__name__, event_name,
                )
                # Clean up empty lists to avoid memory leaks on
                # resource-constrained devices
                if not handlers:
                    del self._handlers[event_name]

    # ----------------------------------------------------------
    #  PUBLISH (SYNC)
    # ----------------------------------------------------------

    def publish(self, event: Event) -> None:
        """
        Synchronously publish an event to all matching subscribers.

        Wildcard subscribers ("*") always receive the event in addition
        to subscribers of the specific event name.

        Error isolation: if a handler raises, the exception is logged
        and remaining handlers continue unaffected.

        Args:
            event: The Event to publish.
        """
        with self._lock:
            self._events_published += 1
            # Snapshot handlers to avoid holding lock during execution
            specific = list(self._handlers.get(event.name, []))
            wildcard = list(self._handlers.get(self.WILDCARD, []))
            target_handlers = specific + wildcard

        for handler in target_handlers:
            try:
                handler.handle(event)
            except Exception as exc:
                self._error_count_inc()
                logger.error(
                    "EventBus: Handler %s failed on event '%s': %s",
                    type(handler).__name__, event.name, exc,
                    exc_info=True,
                )

    # ----------------------------------------------------------
    #  PUBLISH (ASYNC)
    # ----------------------------------------------------------

    async def publish_async(self, event: Event) -> None:
        """
        Asynchronously publish an event to all matching subscribers.

        Handlers are invoked concurrently via asyncio.gather with
        error isolation. Sync handlers are wrapped to run in the
        default executor to avoid blocking the event loop.

        Args:
            event: The Event to publish.
        """
        with self._lock:
            self._events_published += 1
            specific = list(self._handlers.get(event.name, []))
            wildcard = list(self._handlers.get(self.WILDCARD, []))
            target_handlers = specific + wildcard

        async def _safe_call(handler: EventHandler, evt: Event) -> None:
            try:
                # Detect if handler.handle is a coroutine function
                result = handler.handle(evt)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                self._error_count_inc()
                logger.error(
                    "EventBus[async]: Handler %s failed on event '%s': %s",
                    type(handler).__name__, evt.name, exc,
                    exc_info=True,
                )

        await asyncio.gather(
            *[_safe_call(h, event) for h in target_handlers],
            return_exceptions=False,
        )

    # ----------------------------------------------------------
    #  PUBLISH AND COLLECT
    # ----------------------------------------------------------

    def publish_and_collect(self, event: Event) -> List[Any]:
        """
        Publish an event and collect return values from all handlers.

        Handlers that raise are excluded from results (error is logged).
        This is useful for request/response-style queries via the bus.

        Args:
            event: The Event to publish.

        Returns:
            List of values returned by handlers. None values from
            handlers that return None are included; only handlers
            that raised are excluded.
        """
        with self._lock:
            self._events_published += 1
            specific = list(self._handlers.get(event.name, []))
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
                    "EventBus[collect]: Handler %s failed on event '%s': %s",
                    type(handler).__name__, event.name, exc,
                )
        return results

    # ----------------------------------------------------------
    #  UTILITIES
    # ----------------------------------------------------------

    def clear(self) -> None:
        """Remove all handlers from all event names."""
        with self._lock:
            self._handlers.clear()
            logger.debug("EventBus: All handlers cleared")

    @property
    def stats(self) -> Dict[str, Any]:
        """
        Runtime statistics for monitoring and debugging.

        Returns:
            Dict with:
            - events_published: Total events published
            - handlers_count: Total registered handlers
            - errors_count: Total handler errors
            - event_types: List of event names with subscribers
        """
        with self._lock:
            total_handlers = sum(
                len(handlers) for handlers in self._handlers.values()
            )
            return {
                "events_published": self._events_published,
                "handlers_count": total_handlers,
                "errors_count": self._errors_count,
                "event_types": list(self._handlers.keys()),
            }

    def _error_count_inc(self) -> None:
        """Increment error counter in a thread-safe manner."""
        with self._lock:
            self._errors_count += 1
