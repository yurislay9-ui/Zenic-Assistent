"""
Global Health Monitor for v18 agents.

Sliding window of last N calls per agent.
Auto-degrades to fallback-only if unhealthy.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HealthCallRecord:
    """Record of a single agent call for health tracking."""
    success: bool
    latency_s: float
    was_timeout: bool = False
    was_ambiguous: bool = False
    timestamp: float = 0.0


@dataclass
class AgentHealthSnapshot:
    """Health snapshot for a single agent."""
    agent_name: str
    healthy: bool = True
    success_rate: float = 1.0
    avg_latency_s: float = 0.0
    total_calls: int = 0
    recent_calls: int = 0
    timeouts: int = 0
    ambiguous: int = 0
    warning: bool = False


class GlobalHealthMonitor:
    """
    Monitors all agents' health with sliding window.

    Unhealthy threshold: success_rate < 0.3
    Warning threshold: success_rate < 0.7
    """

    def __init__(
        self,
        window_size: int = 50,
        unhealthy_threshold: float = 0.3,
        warning_threshold: float = 0.7,
    ) -> None:
        self.window_size = window_size
        self.unhealthy_threshold = unhealthy_threshold
        self.warning_threshold = warning_threshold

        self._windows: dict[str, deque] = {}
        self._lock = threading.Lock()

    def record_call(
        self,
        agent_name: str,
        success: bool,
        latency_s: float,
        was_timeout: bool = False,
        was_ambiguous: bool = False,
    ) -> None:
        """Record the result of an agent call."""
        with self._lock:
            if agent_name not in self._windows:
                self._windows[agent_name] = deque(maxlen=self.window_size)
            self._windows[agent_name].append(HealthCallRecord(
                success=success,
                latency_s=latency_s,
                was_timeout=was_timeout,
                was_ambiguous=was_ambiguous,
                timestamp=time.monotonic(),
            ))

    def is_healthy(self, agent_name: str) -> bool:
        """Check if an agent is healthy."""
        snapshot = self.get_snapshot(agent_name)
        return snapshot.healthy

    def get_snapshot(self, agent_name: str) -> AgentHealthSnapshot:
        """Get health snapshot for an agent."""
        with self._lock:
            window = self._windows.get(agent_name, deque())
            if not window:
                return AgentHealthSnapshot(agent_name=agent_name, healthy=True, success_rate=1.0)

            records = list(window)
            total = len(records)
            successes = sum(1 for r in records if r.success)
            success_rate = successes / total if total > 0 else 1.0
            avg_latency = sum(r.latency_s for r in records) / total if total > 0 else 0.0
            timeouts = sum(1 for r in records if r.was_timeout)
            ambiguous = sum(1 for r in records if r.was_ambiguous)

            healthy = success_rate >= self.unhealthy_threshold
            warning = success_rate < self.warning_threshold

            return AgentHealthSnapshot(
                agent_name=agent_name,
                healthy=healthy,
                success_rate=success_rate,
                avg_latency_s=avg_latency,
                total_calls=total,
                recent_calls=total,
                timeouts=timeouts,
                ambiguous=ambiguous,
                warning=warning,
            )

    def all_snapshots(self) -> dict[str, AgentHealthSnapshot]:
        """Get health snapshots for all tracked agents."""
        with self._lock:
            names = list(self._windows.keys())
        return {name: self.get_snapshot(name) for name in names}

    def system_health(self) -> dict[str, Any]:
        """Get system-wide health summary."""
        snapshots = self.all_snapshots()
        if not snapshots:
            return {"healthy": True, "agents_tracked": 0, "unhealthy_agents": []}

        unhealthy = [name for name, s in snapshots.items() if not s.healthy]
        warnings = [name for name, s in snapshots.items() if s.warning]
        total = len(snapshots)
        healthy_rate = sum(1 for s in snapshots.values() if s.healthy) / total

        return {
            "healthy": len(unhealthy) == 0,
            "agents_tracked": total,
            "healthy_rate": healthy_rate,
            "unhealthy_agents": unhealthy,
            "warning_agents": warnings,
            "system_alert": len(unhealthy) > total * 0.5,
        }
