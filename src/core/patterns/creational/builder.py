"""
ZENIC-AGENTS - Creational Pattern: Builder

Fluent builder for constructing Orchestrator configuration dicts.
Validates required components before building.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class OrchestratorBuilder:
    """
    Fluent builder that produces a configuration dict for the
    ZENIC-AGENTS Orchestrator.

    Usage (full)::

        config = (
            OrchestratorBuilder()
            .with_model_manager(mm)
            .with_semantic_engine(se)
            .with_mini_ai(ai)
            .with_smart_memory(sm)
            .with_agent_framework(af)
            .with_resource_governor(rg)
            .with_event_bus(eb)
            .with_mediator(med)
            .with_circuit_breaker(cb)
            .with_retry_config(rc)
            .build()
        )

    Usage (minimal)::

        config = (
            OrchestratorBuilder()
            .with_model_manager(mm)
            .with_mini_ai(ai)
            .build_minimal()
        )
    """

    # Required keys for build() – at least these must be set
    _REQUIRED_FULL: Dict[str, str] = {
        "model_manager": "ModelManager",
        "semantic_engine": "SemanticEngine",
        "mini_ai": "MiniAIEngine",
        "smart_memory": "SmartMemory",
        "agent_framework": "AgentFramework",
        "resource_governor": "ResourceGovernor",
        "event_bus": "EventBus",
    }

    # Required keys for build_minimal()
    _REQUIRED_MINIMAL: Dict[str, str] = {
        "model_manager": "ModelManager",
        "mini_ai": "MiniAIEngine",
    }

    def __init__(self) -> None:
        self._config: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Fluent setters
    # ------------------------------------------------------------------

    def with_model_manager(self, mm: Any) -> "OrchestratorBuilder":
        """Set the ModelManager component."""
        self._config["model_manager"] = mm
        return self

    def with_semantic_engine(self, se: Any) -> "OrchestratorBuilder":
        """Set the SemanticEngine component."""
        self._config["semantic_engine"] = se
        return self

    def with_mini_ai(self, ai: Any) -> "OrchestratorBuilder":
        """Set the MiniAIEngine component."""
        self._config["mini_ai"] = ai
        return self

    def with_smart_memory(self, sm: Any) -> "OrchestratorBuilder":
        """Set the SmartMemory component."""
        self._config["smart_memory"] = sm
        return self

    def with_agent_framework(self, af: Any) -> "OrchestratorBuilder":
        """Set the AgentFramework component."""
        self._config["agent_framework"] = af
        return self

    def with_resource_governor(self, rg: Any) -> "OrchestratorBuilder":
        """Set the ResourceGovernor component."""
        self._config["resource_governor"] = rg
        return self

    def with_event_bus(self, eb: Any) -> "OrchestratorBuilder":
        """Set the EventBus component."""
        self._config["event_bus"] = eb
        return self

    def with_mediator(self, med: Any) -> "OrchestratorBuilder":
        """Set the Mediator component."""
        self._config["mediator"] = med
        return self

    def with_circuit_breaker(self, cb: Any) -> "OrchestratorBuilder":
        """Set the CircuitBreaker component."""
        self._config["circuit_breaker"] = cb
        return self

    def with_retry_config(self, rc: Any) -> "OrchestratorBuilder":
        """Set the RetryConfig component."""
        self._config["retry_config"] = rc
        return self

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self) -> Dict[str, Any]:
        """
        Build and validate a full orchestrator configuration dict.

        Returns:
            A dict containing all set components.

        Raises:
            ValueError: If any required component is missing.
        """
        missing = [
            key for key, label in self._REQUIRED_FULL.items()
            if key not in self._config
        ]
        if missing:
            labels = [self._REQUIRED_FULL[k] for k in missing]
            raise ValueError(
                f"OrchestratorBuilder: missing required components: {', '.join(labels)}"
            )
        logger.debug(
            "OrchestratorBuilder: built full config with %d components",
            len(self._config),
        )
        return dict(self._config)

    def build_minimal(self) -> Dict[str, Any]:
        """
        Build a minimal orchestrator configuration dict.

        Only ``model_manager`` and ``mini_ai`` are required.

        Returns:
            A dict containing all set components.

        Raises:
            ValueError: If any minimal required component is missing.
        """
        missing = [
            key for key, label in self._REQUIRED_MINIMAL.items()
            if key not in self._config
        ]
        if missing:
            labels = [self._REQUIRED_MINIMAL[k] for k in missing]
            raise ValueError(
                f"OrchestratorBuilder: missing minimal components: {', '.join(labels)}"
            )
        logger.debug(
            "OrchestratorBuilder: built minimal config with %d components",
            len(self._config),
        )
        return dict(self._config)
