"""
ZENIC-AGENTS - Creational Pattern: Prototype

Clone existing agent instances via deep copy with optional overrides.
Useful for spawning multiple similar agents without repeated setup.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
"""

import copy
import logging
import threading
from typing import Any, Dict, Optional, Type

from src.core.agents.base import BaseAgent

logger = logging.getLogger(__name__)


def _is_thread_primitive(value: Any) -> bool:
    """Return True if *value* is a threading lock/condition (unpicklable)."""
    type_name = type(value).__name__
    return type_name in ("lock", "RLock", "Condition", "_thread.lock", "_thread.RLock")


def _make_fresh_thread_primitive(value: Any) -> Any:
    """Create a fresh threading primitive matching the type of *value*."""
    type_name = type(value).__name__
    if type_name == "Condition" or hasattr(value, "wait"):
        return threading.Condition()
    if type_name in ("RLock", "_thread.RLock") or (hasattr(value, "_is_owned")):
        return threading.RLock()
    # Default: plain Lock
    return threading.Lock()


def _safe_deepcopy_agent(agent: BaseAgent) -> BaseAgent:
    """
    Deep-copy a BaseAgent instance, replacing unpicklable threading
    primitives (locks, etc.) with fresh ones on the clone.

    Standard ``copy.deepcopy`` fails on objects that contain
    ``threading.Lock`` (or RLock) because locks cannot be pickled.
    This function works around that by:

      1. Extracting the agent's ``__dict__``.
      2. Temporarily replacing threading primitives with placeholders.
      3. Deep-copying the cleaned dict.
      4. Constructing a new instance via ``__new__`` and restoring
         the copied state plus fresh threading primitives.
    """
    # Identify threading primitives in the agent's __dict__
    thread_attrs: Dict[str, Any] = {}
    clean_dict: Dict[str, Any] = {}
    for key, value in agent.__dict__.items():
        if _is_thread_primitive(value):
            thread_attrs[key] = value
            clean_dict[key] = None  # placeholder
        else:
            clean_dict[key] = value

    # Deep-copy the clean dict
    copied_dict = copy.deepcopy(clean_dict)

    # Create a new instance without calling __init__
    cloned = object.__new__(type(agent))
    # Restore copied state
    cloned.__dict__.update(copied_dict)
    # Replace thread primitives with fresh instances
    for key, orig in thread_attrs.items():
        cloned.__dict__[key] = _make_fresh_thread_primitive(orig)

    return cloned


class AgentPrototype:
    """
    Prototype that stores a :class:`BaseAgent` instance and produces
    deep-copied clones with optional attribute overrides.

    The stored prototype is **never** mutated; every clone is an
    independent deep copy.

    Usage::

        proto = AgentPrototype(some_agent)
        clone1 = proto.clone()                          # exact copy
        clone2 = proto.clone(name="other")              # copy with name override
        clone3 = proto.clone_with_config({"model": "x"}) # copy with new config
    """

    def __init__(self, agent_instance: BaseAgent) -> None:
        """
        Store *agent_instance* as the prototype template.

        Args:
            agent_instance: A fully configured :class:`BaseAgent` to clone from.

        Raises:
            ValueError: If *agent_instance* is not a BaseAgent.
        """
        if not isinstance(agent_instance, BaseAgent):
            raise ValueError(
                "AgentPrototype: agent_instance must be a BaseAgent instance"
            )
        self._prototype: BaseAgent = agent_instance
        logger.debug(
            "AgentPrototype: stored prototype for agent '%s'",
            agent_instance.name,
        )

    # ------------------------------------------------------------------
    # Cloning
    # ------------------------------------------------------------------

    def clone(self, **overrides: Any) -> BaseAgent:
        """
        Deep-copy the prototype and apply attribute overrides.

        Each keyword argument is set as an attribute on the new clone
        **after** deep-copying, so mutable overrides replace the copied
        value entirely.

        Args:
            **overrides: Attribute names and values to override on the clone.

        Returns:
            A new :class:`BaseAgent` instance (deep copy of prototype).
        """
        cloned: BaseAgent = _safe_deepcopy_agent(self._prototype)
        for key, value in overrides.items():
            setattr(cloned, key, value)
        logger.debug(
            "AgentPrototype: cloned agent '%s' with overrides %s",
            cloned.name,
            list(overrides.keys()) if overrides else "(none)",
        )
        return cloned

    def clone_with_config(self, config: Dict[str, Any]) -> BaseAgent:
        """
        Deep-copy the prototype and apply a configuration dict.

        Each key-value pair in *config* is set as an attribute on the
        clone, similar to :meth:`clone` but accepting a dict instead of
        keyword arguments.

        Args:
            config: Dict of attribute names → values to override.

        Returns:
            A new :class:`BaseAgent` instance.

        Raises:
            ValueError: If *config* is not a dict.
        """
        if not isinstance(config, dict):
            raise ValueError("AgentPrototype: config must be a dict")
        return self.clone(**config)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def prototype(self) -> BaseAgent:
        """Return the stored prototype (do NOT mutate)."""
        return self._prototype

    @property
    def prototype_name(self) -> str:
        """Return the name of the stored prototype agent."""
        return self._prototype.name
