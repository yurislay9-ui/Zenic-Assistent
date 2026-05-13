"""
ZENIC-AGENTS - Creational Pattern: Factory

Thread-safe factory and registry for creating agent instances.
Designed for resource-constrained environments (Android/Termux, 500MB RAM).

Classes:
  FactoryRegistry: Generic registry for named creator functions.
  AgentFactory: Specialized factory for creating BaseAgent instances with
                default configs and per-call overrides.
"""

import threading
import logging
import copy
from typing import Any, Callable, Dict, List, Optional, Type

from src.core.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class FactoryRegistry:
    """
    Generic thread-safe registry for named creator functions.

    Usage::

        registry = FactoryRegistry()
        registry.register("widget", lambda: Widget())
        obj = registry.create("widget")
    """

    def __init__(self) -> None:
        self._creators: Dict[str, Callable[..., Any]] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, name: str, creator_fn: Callable[..., Any]) -> None:
        """
        Register a creator function under *name*.

        Args:
            name: Unique identifier for the creator.
            creator_fn: Callable that produces an object.

        Raises:
            ValueError: If *name* is empty or *creator_fn* is not callable.
        """
        if not name:
            raise ValueError("FactoryRegistry: name must be a non-empty string")
        if not callable(creator_fn):
            raise ValueError(f"FactoryRegistry: creator_fn for '{name}' must be callable")
        with self._lock:
            if name in self._creators:
                logger.debug("FactoryRegistry: overwriting existing creator '%s'", name)
            self._creators[name] = creator_fn
            logger.debug("FactoryRegistry: registered creator '%s'", name)

    def create(self, name: str, **kwargs: Any) -> Any:
        """
        Create an object by invoking the registered creator.

        Args:
            name: Registered creator name.
            **kwargs: Forwarded to the creator function.

        Returns:
            The object produced by the creator.

        Raises:
            KeyError: If *name* is not registered.
        """
        with self._lock:
            creator = self._creators.get(name)
        if creator is None:
            raise KeyError(f"FactoryRegistry: no creator registered as '{name}'")
        return creator(**kwargs)

    def list_registered(self) -> List[str]:
        """Return a sorted list of all registered creator names."""
        with self._lock:
            return sorted(self._creators.keys())

    def has(self, name: str) -> bool:
        """Return True if a creator is registered under *name*."""
        with self._lock:
            return name in self._creators


class AgentFactory:
    """
    Thread-safe factory for creating :class:`BaseAgent` instances.

    Each agent type is registered with a class and a *default_config* dict.
    At creation time the defaults are deep-copied and merged with any
    per-call overrides so that registrations remain immutable.

    Usage::

        factory = AgentFactory()
        factory.register_agent("intent", IntentAgent, {"model": "qwen3"})
        agent = factory.create_agent("intent", model="qwen3-4b")
    """

    def __init__(self) -> None:
        self._registry: Dict[str, Dict[str, Any]] = {}  # name -> {class, default_config}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_agent(
        self,
        agent_type: str,
        agent_class: Type[BaseAgent],
        default_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register an agent type.

        Args:
            agent_type: Unique string identifier (e.g. ``"intent"``).
            agent_class: Concrete subclass of :class:`BaseAgent`.
            default_config: Default keyword arguments passed to the constructor.

        Raises:
            ValueError: If *agent_type* is empty or *agent_class* is not a
                        BaseAgent subclass.
        """
        if not agent_type:
            raise ValueError("AgentFactory: agent_type must be a non-empty string")
        if not (isinstance(agent_class, type) and issubclass(agent_class, BaseAgent)):
            raise ValueError(
                f"AgentFactory: agent_class for '{agent_type}' must be a BaseAgent subclass"
            )
        config = default_config or {}
        with self._lock:
            if agent_type in self._registry:
                logger.debug("AgentFactory: overwriting existing agent type '%s'", agent_type)
            self._registry[agent_type] = {
                "class": agent_class,
                "default_config": copy.deepcopy(config),
            }
            logger.debug("AgentFactory: registered agent type '%s'", agent_type)

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create_agent(self, agent_type: str, **overrides: Any) -> BaseAgent:
        """
        Create an agent instance of the given type.

        The default config is deep-copied and then merged with *overrides*
        (overrides take precedence).

        Args:
            agent_type: Previously registered agent type name.
            **overrides: Keyword arguments that override default config values.

        Returns:
            A new :class:`BaseAgent` instance.

        Raises:
            KeyError: If *agent_type* is not registered.
        """
        with self._lock:
            entry = self._registry.get(agent_type)
        if entry is None:
            raise KeyError(f"AgentFactory: no agent type registered as '{agent_type}'")

        agent_class: Type[BaseAgent] = entry["class"]
        merged_config = copy.deepcopy(entry["default_config"])
        merged_config.update(overrides)

        agent = agent_class(**merged_config)
        logger.debug(
            "AgentFactory: created agent '%s' (class=%s, config_keys=%s)",
            agent_type,
            agent_class.__name__,
            list(merged_config.keys()),
        )
        return agent

    def create_from_config(self, config: Dict[str, Any]) -> BaseAgent:
        """
        Create an agent from a full configuration dict.

        Expected keys in *config*:

        - ``agent_type`` (str): registered agent type name.
        - All other keys are forwarded as constructor keyword arguments,
          **replacing** (not merging with) the stored defaults.

        Args:
            config: Full configuration dictionary.

        Returns:
            A new :class:`BaseAgent` instance.

        Raises:
            KeyError: If ``agent_type`` is missing or not registered.
            ValueError: If *config* is not a dict.
        """
        if not isinstance(config, dict):
            raise ValueError("AgentFactory: config must be a dict")
        agent_type = config.get("agent_type")
        if not agent_type:
            raise KeyError("AgentFactory: config must contain 'agent_type' key")
        overrides = {k: v for k, v in config.items() if k != "agent_type"}
        return self.create_agent(agent_type, **overrides)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_agent_types(self) -> List[str]:
        """Return a sorted list of all registered agent type names."""
        with self._lock:
            return sorted(self._registry.keys())

    def get_default_config(self, agent_type: str) -> Dict[str, Any]:
        """
        Return a **deep copy** of the default config for *agent_type*.

        Raises:
            KeyError: If *agent_type* is not registered.
        """
        with self._lock:
            entry = self._registry.get(agent_type)
        if entry is None:
            raise KeyError(f"AgentFactory: no agent type registered as '{agent_type}'")
        return copy.deepcopy(entry["default_config"])
