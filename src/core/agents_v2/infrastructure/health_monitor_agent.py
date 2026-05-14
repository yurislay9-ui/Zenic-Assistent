"""
A45 HealthMonitorAgent — SINGLE RESPONSIBILITY: Track health of all agents and LLM.

Wraps GlobalHealthMonitor as a BaseAgent so it can participate in the
agent pipeline. Provides system-wide and per-agent health snapshots.

Ported from:
  - resilience/health_monitor.py (GlobalHealthMonitor)
"""

from __future__ import annotations

import time
from typing import Any, Optional

from ..resilience import BaseAgent, GlobalHealthMonitor, AgentHealthSnapshot
from ..schemas import HealthSnapshot, CircuitState


class HealthMonitorAgent(BaseAgent[HealthSnapshot]):
    """
    A45: Track health of all agents and LLM.

    Single Responsibility: Health monitoring ONLY.
    Method: Query GlobalHealthMonitor for snapshots and system status.
    Fallback: Return healthy snapshot (assume healthy when no data).
    """

    def __init__(
        self,
        health_monitor: Optional[GlobalHealthMonitor] = None,
        **kwargs,
    ) -> None:
        super().__init__(name="A45_HealthMonitor", **kwargs)
        self._monitor = health_monitor or GlobalHealthMonitor()

    def execute(self, input_data: Any) -> HealthSnapshot:
        """
        Get health snapshot.

        input_data can be:
          - None or "all": system-wide snapshot
          - dict with 'agent_name': str → per-agent snapshot
          - dict with 'action': "system"|"agent"|"unhealthy" → specific query
        """
        action = "system"
        agent_name = ""

        if isinstance(input_data, dict):
            action = input_data.get("action", "system")
            agent_name = input_data.get("agent_name", "")
        elif isinstance(input_data, str):
            if input_data == "all":
                action = "system"
            else:
                action = "agent"
                agent_name = input_data

        if action == "agent" and agent_name:
            return self._get_agent_snapshot(agent_name)
        elif action == "unhealthy":
            return self._get_unhealthy_snapshot()
        else:
            return self._get_system_snapshot()

    def _get_system_snapshot(self) -> HealthSnapshot:
        """Get system-wide health snapshot."""
        system = self._monitor.system_health()
        snapshots = self._monitor.all_snapshots()

        success_rates = {}
        latencies = {}

        for name, snap in snapshots.items():
            success_rates[name] = round(snap.success_rate, 3)
            latencies[name] = round(snap.avg_latency_s * 1000, 1)  # ms

        return HealthSnapshot(
            healthy=system.get("healthy", True),
            success_rates=success_rates,
            latencies=latencies,
            circuit_breaker_states={},  # Filled by CircuitBreakerManagerAgent
            timestamp=time.monotonic(),
            source="deterministic",
        )

    def _get_agent_snapshot(self, agent_name: str) -> HealthSnapshot:
        """Get per-agent health snapshot."""
        snap = self._monitor.get_snapshot(agent_name)
        # Unknown agents have no data — report as unknown, not healthy
        if snap.total_calls == 0:
            return HealthSnapshot(
                healthy=False,
                success_rates={agent_name: 0.0},
                latencies={agent_name: 0.0},
                circuit_breaker_states={},
                timestamp=time.monotonic(),
                source="deterministic",
            )

        return HealthSnapshot(
            healthy=snap.healthy,
            success_rates={agent_name: round(snap.success_rate, 3)},
            latencies={agent_name: round(snap.avg_latency_s * 1000, 1)},
            circuit_breaker_states={},
            timestamp=time.monotonic(),
            source="deterministic",
        )

    def _get_unhealthy_snapshot(self) -> HealthSnapshot:
        """Get snapshot of only unhealthy agents."""
        system = self._monitor.system_health()
        unhealthy_names = system.get("unhealthy_agents", [])
        warning_names = system.get("warning_agents", [])

        all_problematic = list(set(unhealthy_names + warning_names))
        success_rates = {}
        latencies = {}

        for name in all_problematic:
            snap = self._monitor.get_snapshot(name)
            success_rates[name] = round(snap.success_rate, 3)
            latencies[name] = round(snap.avg_latency_s * 1000, 1)

        return HealthSnapshot(
            healthy=len(unhealthy_names) == 0,
            success_rates=success_rates,
            latencies=latencies,
            circuit_breaker_states={},
            timestamp=time.monotonic(),
            source="deterministic",
        )

    def record_call(
        self,
        agent_name: str,
        success: bool,
        latency_s: float,
        was_timeout: bool = False,
    ) -> None:
        """Record an agent call result (called by AgentRunner after execution)."""
        self._monitor.record_call(
            agent_name=agent_name,
            success=success,
            latency_s=latency_s,
            was_timeout=was_timeout,
        )

    def is_healthy(self, agent_name: str) -> bool:
        """Quick health check for a specific agent."""
        return self._monitor.is_healthy(agent_name)

    def fallback(self, input_data: Any) -> HealthSnapshot:
        """Fallback: Assume healthy when no data available."""
        return HealthSnapshot(
            healthy=True,
            timestamp=time.monotonic(),
            source="fallback",
        )
