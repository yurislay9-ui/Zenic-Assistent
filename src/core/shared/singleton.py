"""
ZENIC-AGENTS — Thread-safe Singleton Factory.

Provides a consistent, thread-safe singleton pattern with:
- Double-checked locking for performance
- Thread-safe init() with guard against double initialization
- Reset for testing

All project singletons should use this class instead of
ad-hoc global + lock patterns.
"""

import logging
import threading
from typing import Callable, Generic, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Singleton(Generic[T]):
    """Thread-safe singleton with double-checked locking.

    Usage::

        my_singleton = Singleton(lambda: ExpensiveObject(), name="ExpensiveObject")
        instance = my_singleton.get()
        my_singleton.reset()  # For testing only

    Or with init() for custom construction::

        my_singleton = Singleton(lambda: None, name="ExpensiveObject")
        my_singleton.init(lambda: ExpensiveObject(config="custom"))
        instance = my_singleton.get()
    """

    def __init__(self, factory: Callable[[], T], name: str = "") -> None:
        self._factory = factory
        self._name = name or getattr(factory, "__qualname__", "Singleton")
        self._instance: Optional[T] = None
        self._lock = threading.Lock()

    def get(self) -> T:
        """Get or create the singleton instance (double-checked locking)."""
        if self._instance is None:
            with self._lock:
                if self._instance is None:
                    self._instance = self._factory()
                    logger.debug("Singleton %s: instance created", self._name)
        return self._instance

    def init(self, factory: Callable[[], T]) -> T:
        """Initialize with a custom factory (thread-safe).

        Replaces the default factory and creates the instance.
        Raises RuntimeError if already initialized — call reset() first.

        Args:
            factory: Callable that creates the singleton instance.

        Returns:
            The newly created instance.

        Raises:
            RuntimeError: If the singleton is already initialized.
        """
        with self._lock:
            if self._instance is not None:
                raise RuntimeError(
                    f"Singleton '{self._name}' is already initialized. "
                    f"Call reset() first if you need to reinitialize."
                )
            self._factory = factory
            self._instance = self._factory()
            logger.info("Singleton %s: initialized with custom factory", self._name)
        return self._instance

    def reset(self) -> None:
        """Reset the singleton (for testing only).

        After reset, the next get() call will create a new instance.
        """
        with self._lock:
            if self._instance is not None:
                logger.debug("Singleton %s: reset", self._name)
            self._instance = None

    @property
    def is_initialized(self) -> bool:
        """Check if the singleton has been created."""
        return self._instance is not None
