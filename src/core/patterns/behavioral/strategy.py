"""
ZENIC-AGENTS - Behavioral Pattern: Strategy

Thread-safe strategy registry with default strategy support and metadata.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
"""

import logging
import threading
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """
    Thread-safe registry for named strategy callables.

    Each strategy is registered with a name, a callable, and optional
    metadata.  A *default* strategy can be designated per category.

    Usage::

        reg = StrategyRegistry()
        reg.register("bfs", bfs_traverse, metadata={"category": "traversal"})
        reg.register("dfs", dfs_traverse, metadata={"category": "traversal"})
        reg.default_strategy("bfs")
        result = reg.execute("bfs", graph)
    """

    def __init__(self) -> None:
        self._strategies: Dict[str, Callable[..., Any]] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._defaults: Dict[str, str] = {}  # category → strategy name
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        strategy: Callable[..., Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register a strategy callable under *name*.

        Args:
            name: Unique strategy identifier.
            strategy: Callable implementing the strategy.
            metadata: Optional dict of metadata (e.g. ``{"category": "x"}``).

        Raises:
            ValueError: If *name* is empty or *strategy* is not callable.
        """
        if not name:
            raise ValueError("StrategyRegistry: name must be a non-empty string")
        if not callable(strategy):
            raise ValueError(
                f"StrategyRegistry: strategy for '{name}' must be callable"
            )
        with self._lock:
            if name in self._strategies:
                logger.debug("StrategyRegistry: overwriting strategy '%s'", name)
            self._strategies[name] = strategy
            self._metadata[name] = dict(metadata) if metadata else {}
            logger.debug("StrategyRegistry: registered strategy '%s'", name)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get(self, name: str) -> Callable[..., Any]:
        """
        Retrieve a strategy callable by name.

        Raises:
            KeyError: If *name* is not registered.
        """
        with self._lock:
            strategy = self._strategies.get(name)
        if strategy is None:
            raise KeyError(f"StrategyRegistry: no strategy registered as '{name}'")
        return strategy

    def execute(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """
        Execute a strategy by name.

        Args:
            name: Registered strategy name.
            *args: Positional arguments forwarded to the strategy.
            **kwargs: Keyword arguments forwarded to the strategy.

        Returns:
            The result of the strategy call.

        Raises:
            KeyError: If *name* is not registered.
        """
        strategy = self.get(name)
        return strategy(*args, **kwargs)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_strategies(self) -> List[str]:
        """Return a sorted list of all registered strategy names."""
        with self._lock:
            return sorted(self._strategies.keys())

    def get_metadata(self, name: str) -> Dict[str, Any]:
        """
        Return metadata for a registered strategy.

        Raises:
            KeyError: If *name* is not registered.
        """
        with self._lock:
            if name not in self._metadata:
                raise KeyError(f"StrategyRegistry: no strategy registered as '{name}'")
            return dict(self._metadata[name])

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------

    def default_strategy(self, name: str) -> None:
        """
        Set the strategy *name* as the default for its category.

        The category is read from the strategy's metadata ``"category"`` key.
        If no category is set, the special category ``"__default__"`` is used.

        Args:
            name: Name of a registered strategy.

        Raises:
            KeyError: If *name* is not registered.
        """
        with self._lock:
            if name not in self._strategies:
                raise KeyError(f"StrategyRegistry: no strategy registered as '{name}'")
            category = self._metadata.get(name, {}).get("category", "__default__")
            self._defaults[category] = name
            logger.debug(
                "StrategyRegistry: set default strategy for category '%s' → '%s'",
                category, name,
            )

    def get_default(self, category: str = "__default__") -> Optional[Callable[..., Any]]:
        """
        Return the default strategy callable for *category*, or None.
        """
        with self._lock:
            name = self._defaults.get(category)
        if name is None:
            return None
        return self.get(name)
