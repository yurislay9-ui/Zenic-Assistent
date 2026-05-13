"""
ZENIC-AGENTS - Architectural Pattern: CQRS

Command Query Responsibility Segregation bus.

Separates write operations (Commands) from read operations (Queries),
with validation middleware for commands and caching middleware for queries.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
"""

import logging
import threading
import time
import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ======================================================================
# Data classes
# ======================================================================

@dataclass
class Command:
    """
    Represents a **write** operation (mutates state).

    Attributes:
        command_type: Unique identifier for the command kind.
        payload: Dict of command-specific data.
    """
    command_type: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Query:
    """
    Represents a **read** operation (no side effects).

    Attributes:
        query_type: Unique identifier for the query kind.
        params: Dict of query-specific parameters.
    """
    query_type: str
    params: Dict[str, Any] = field(default_factory=dict)


# ======================================================================
# Handler ABCs
# ======================================================================

class CommandHandler(ABC):
    """Abstract handler for :class:`Command` objects."""

    @abstractmethod
    def handle(self, command: Command) -> Dict[str, Any]:
        """
        Process a command and return a result dict.

        Args:
            command: The command to handle.

        Returns:
            A dict with at least a ``"success"`` key.
        """
        ...


class QueryHandler(ABC):
    """Abstract handler for :class:`Query` objects."""

    @abstractmethod
    def handle(self, query: Query) -> Dict[str, Any]:
        """
        Process a query and return a result dict.

        Args:
            query: The query to handle.

        Returns:
            A dict with the query results.
        """
        ...


# ======================================================================
# CQRS Bus
# ======================================================================

class CQRSBus:
    """
    Central bus that dispatches Commands and Queries to their
    registered handlers.

    Features:
      - **Validation middleware** for commands: validators are called
        before the handler; a failed validation rejects the command.
      - **Caching middleware** for queries: results are cached with a
        configurable TTL.
      - Thread-safe.

    Usage::

        bus = CQRSBus()
        bus.register_command_handler("create_user", CreateUserHandler())
        bus.register_query_handler("get_user", GetUserHandler())
        bus.register_command_validator("create_user", validate_user)

        result = bus.execute_command(Command("create_user", {"name": "Alice"}))
        user = bus.execute_query(Query("get_user", {"id": 1}))
    """

    def __init__(self, query_cache_ttl: float = 300.0) -> None:
        """
        Args:
            query_cache_ttl: Default TTL (seconds) for cached query results.
        """
        self._command_handlers: Dict[str, CommandHandler] = {}
        self._query_handlers: Dict[str, QueryHandler] = {}
        self._command_validators: Dict[str, List[Callable[[Command], bool]]] = {}
        self._query_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
        self._query_cache_ttl = query_cache_ttl
        self._lock = threading.RLock()
        # Stats
        self._commands_executed = 0
        self._commands_failed = 0
        self._queries_executed = 0
        self._query_cache_hits = 0

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_command_handler(
        self, command_type: str, handler: CommandHandler
    ) -> None:
        """
        Register a handler for a command type.

        Args:
            command_type: Command type identifier.
            handler: A :class:`CommandHandler` instance.

        Raises:
            ValueError: If arguments are invalid.
        """
        if not command_type:
            raise ValueError("CQRSBus: command_type must be a non-empty string")
        if not isinstance(handler, CommandHandler):
            raise ValueError("CQRSBus: handler must be a CommandHandler instance")
        with self._lock:
            self._command_handlers[command_type] = handler
            logger.debug("CQRSBus: registered command handler for '%s'", command_type)

    def register_query_handler(
        self, query_type: str, handler: QueryHandler
    ) -> None:
        """
        Register a handler for a query type.

        Args:
            query_type: Query type identifier.
            handler: A :class:`QueryHandler` instance.

        Raises:
            ValueError: If arguments are invalid.
        """
        if not query_type:
            raise ValueError("CQRSBus: query_type must be a non-empty string")
        if not isinstance(handler, QueryHandler):
            raise ValueError("CQRSBus: handler must be a QueryHandler instance")
        with self._lock:
            self._query_handlers[query_type] = handler
            logger.debug("CQRSBus: registered query handler for '%s'", query_type)

    def register_command_validator(
        self,
        command_type: str,
        validator: Callable[[Command], bool],
    ) -> None:
        """
        Register a validation function for a command type.

        Validators are called **before** the handler.  If any validator
        returns ``False``, the command is rejected.

        Multiple validators can be registered per command type; all must
        pass.

        Args:
            command_type: Command type identifier.
            validator: Callable that takes a :class:`Command` and returns
                       ``True`` if valid.

        Raises:
            ValueError: If arguments are invalid.
        """
        if not command_type:
            raise ValueError("CQRSBus: command_type must be a non-empty string")
        if not callable(validator):
            raise ValueError("CQRSBus: validator must be callable")
        with self._lock:
            if command_type not in self._command_validators:
                self._command_validators[command_type] = []
            self._command_validators[command_type].append(validator)
            logger.debug(
                "CQRSBus: registered validator for command '%s'", command_type
            )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute_command(self, command: Command) -> Dict[str, Any]:
        """
        Dispatch a command to its registered handler.

        Validation middleware runs first.  If any validator rejects the
        command, ``{"success": False, "error": "validation_failed"}`` is
        returned and the handler is **not** called.

        Args:
            command: The :class:`Command` to execute.

        Returns:
            Result dict from the handler, or an error dict.

        Raises:
            KeyError: If no handler is registered for the command type.
        """
        with self._lock:
            handler = self._command_handlers.get(command.command_type)
            validators = list(self._command_validators.get(command.command_type, []))

        if handler is None:
            raise KeyError(
                f"CQRSBus: no handler registered for command '{command.command_type}'"
            )

        # Validation middleware
        for validator in validators:
            try:
                if not validator(command):
                    with self._lock:
                        self._commands_failed += 1
                        self._commands_executed += 1
                    logger.warning(
                        "CQRSBus: command '%s' rejected by validator",
                        command.command_type,
                    )
                    return {"success": False, "error": "validation_failed"}
            except Exception as exc:
                with self._lock:
                    self._commands_failed += 1
                    self._commands_executed += 1
                logger.error("CQRSBus: validator error – %s", exc)
                return {"success": False, "error": f"validator_error: {exc}"}

        # Execute handler
        try:
            result = handler.handle(command)
            with self._lock:
                self._commands_executed += 1
            if not isinstance(result, dict):
                result = {"success": True, "data": result}
            return result
        except Exception as exc:
            with self._lock:
                self._commands_executed += 1
                self._commands_failed += 1
            logger.error(
                "CQRSBus: command '%s' handler failed – %s",
                command.command_type, exc,
            )
            return {"success": False, "error": str(exc)}

    def execute_query(self, query: Query) -> Dict[str, Any]:
        """
        Dispatch a query to its registered handler.

        Caching middleware checks for a cached result before invoking
        the handler.  Cache key is derived from ``query_type`` and
        ``params``.

        Args:
            query: The :class:`Query` to execute.

        Returns:
            Result dict from the handler (or cache).

        Raises:
            KeyError: If no handler is registered for the query type.
        """
        cache_key = self._make_cache_key(query)

        # Check cache
        with self._lock:
            cached = self._query_cache.get(cache_key)
            if cached is not None:
                result, ts = cached
                if (time.monotonic() - ts) < self._query_cache_ttl:
                    self._query_cache_hits += 1
                    self._queries_executed += 1
                    logger.debug(
                        "CQRSBus: query '%s' cache HIT", query.query_type
                    )
                    return copy.deepcopy(result)
                # Expired — remove
                del self._query_cache[cache_key]

            handler = self._query_handlers.get(query.query_type)

        if handler is None:
            raise KeyError(
                f"CQRSBus: no handler registered for query '{query.query_type}'"
            )

        # Execute handler
        try:
            result = handler.handle(query)
            with self._lock:
                self._queries_executed += 1
                self._query_cache[cache_key] = (copy.deepcopy(result), time.monotonic())
            logger.debug("CQRSBus: query '%s' executed and cached", query.query_type)
            return result
        except Exception as exc:
            with self._lock:
                self._queries_executed += 1
            logger.error(
                "CQRSBus: query '%s' handler failed – %s",
                query.query_type, exc,
            )
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def invalidate_query_cache(self, query_type: Optional[str] = None) -> None:
        """
        Clear cached query results.

        Args:
            query_type: If given, only clear entries for this query type.
                        If None, clear the entire query cache.
        """
        with self._lock:
            if query_type is None:
                self._query_cache.clear()
                logger.debug("CQRSBus: cleared entire query cache")
            else:
                keys_to_remove = [
                    k for k in self._query_cache
                    if k.startswith(f"{query_type}:")
                ]
                for k in keys_to_remove:
                    del self._query_cache[k]
                logger.debug(
                    "CQRSBus: cleared %d cache entries for query '%s'",
                    len(keys_to_remove), query_type,
                )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def stats(self) -> Dict[str, Any]:
        """Return bus statistics."""
        with self._lock:
            total_queries = max(self._queries_executed, 1)
            return {
                "commands_executed": self._commands_executed,
                "commands_failed": self._commands_failed,
                "queries_executed": self._queries_executed,
                "query_cache_hits": self._query_cache_hits,
                "query_cache_hit_rate": self._query_cache_hits / total_queries,
                "query_cache_entries": len(self._query_cache),
                "registered_command_handlers": list(self._command_handlers.keys()),
                "registered_query_handlers": list(self._query_handlers.keys()),
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _make_cache_key(query: Query) -> str:
        """Produce a deterministic cache key from a query."""
        try:
            params_str = repr(sorted(query.params.items()))
        except Exception:
            params_str = str(id(query.params))
        return f"{query.query_type}:{params_str}"
