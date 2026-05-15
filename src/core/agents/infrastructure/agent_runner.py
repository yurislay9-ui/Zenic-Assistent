"""
A44 AgentRunner — SINGLE RESPONSIBILITY: Execute an agent with full resilience.

Wraps any BaseAgent execution with circuit breaker, retry with exponential
backoff, bulkhead concurrency limiting, health monitoring, and audit logging.

This is the ONLY sanctioned way to run an agent in the v18 architecture.
Direct calls to agent.execute() bypass resilience — always use AgentRunner.

Ported from:
  - resilience/base_agent.py (run() method)
  - Original AgentRunner from agents/runner
"""

from __future__ import annotations

import time
import threading
from typing import Any, Optional, Type

from ..resilience import BaseAgent, AgentRetryConfig, CircuitBreakerManager, BulkheadManager, GlobalHealthMonitor, AuditLogger, AuditEntry
from ..schemas import AgentResult


class AgentRunner(BaseAgent[AgentResult]):
    """
    A44: Execute agents with full resilience patterns.

    Single Responsibility: Agent execution with resilience ONLY.
    Method: Wrap agent calls in circuit breaker + retry + bulkhead + audit.
    Fallback: Return AgentResult with success=False.
    """

    def __init__(
        self,
        circuit_breaker_manager: Optional[CircuitBreakerManager] = None,
        bulkhead_manager: Optional[BulkheadManager] = None,
        health_monitor: Optional[GlobalHealthMonitor] = None,
        audit_logger: Optional[AuditLogger] = None,
        retry_config: Optional[AgentRetryConfig] = None,
        **kwargs,
    ) -> None:
        super().__init__(
            name="A44_AgentRunner",
            circuit_breaker_manager=circuit_breaker_manager,
            bulkhead_manager=bulkhead_manager,
            health_monitor=health_monitor,
            audit_logger=audit_logger,
            retry_config=retry_config,
            **kwargs,
        )
        self._registered_agents: dict[str, BaseAgent] = {}
        self._registry_lock = threading.Lock()

    # ──────────────────────────────────────────────────────────
    # AGENT REGISTRY
    # ──────────────────────────────────────────────────────────

    def register(self, agent: BaseAgent) -> None:
        """Register an agent for execution by name."""
        with self._registry_lock:
            self._registered_agents[agent.name] = agent

    def register_many(self, agents: list) -> None:
        """Register multiple agents at once."""
        for agent in agents:
            self.register(agent)

    def get_agent(self, name: str) -> Optional[BaseAgent]:
        """Get a registered agent by name."""
        with self._registry_lock:
            return self._registered_agents.get(name)

    @property
    def registered_names(self) -> list:
        """List all registered agent names."""
        with self._registry_lock:
            return list(self._registered_agents.keys())

    # ──────────────────────────────────────────────────────────
    # EXECUTION (implements BaseAgent)
    # ──────────────────────────────────────────────────────────

    def execute(self, input_data: Any) -> AgentResult:
        """
        Execute a registered agent with full resilience.

        input_data must be a dict with:
          - 'agent_name': str (name of registered agent)
          - 'input': Any (data to pass to the agent)
          OR
          - 'agent': BaseAgent instance (direct execution, no registry lookup)
          - 'input': Any

        Returns AgentResult with full execution metadata.
        """
        if not isinstance(input_data, dict):
            return self.fallback(input_data)

        # Resolve agent
        agent = input_data.get("agent")
        agent_name = input_data.get("agent_name", "")
        agent_input = input_data.get("input")

        if agent is None and agent_name:
            agent = self.get_agent(agent_name)

        if agent is None or not isinstance(agent, BaseAgent):
            return AgentResult(
                success=False,
                source="error",
                error=f"Agent not found: {agent_name or 'None'}",
            )

        # Execute via the agent's built-in run() (which has resilience)
        result = agent.run(agent_input)

        # Normalize to AgentResult
        if isinstance(result, dict):
            return AgentResult(
                success=result.get("success", False),
                data=result.get("data"),
                source=result.get("source", "deterministic"),
                duration_ms=result.get("duration_ms", 0.0),
                error=result.get("error", ""),
            )

        return AgentResult(
            success=True,
            data=result,
            source="deterministic",
        )

    def run_agent(self, agent_name: str, input_data: Any) -> dict[str, Any]:
        """
        Convenience method: Run a registered agent by name.

        Returns the raw run() result dict from BaseAgent.
        """
        agent = self.get_agent(agent_name)
        if agent is None:
            return {
                "success": False,
                "data": None,
                "source": "error",
                "duration_ms": 0.0,
                "retry_count": 0,
                "agent": agent_name,
                "error": f"Agent not registered: {agent_name}",
            }
        return agent.run(input_data)

    def fallback(self, input_data: Any) -> AgentResult:
        """Fallback: Return failure result."""
        return AgentResult(
            success=False,
            source="fallback",
            error="AgentRunner fallback: could not execute agent",
        )
