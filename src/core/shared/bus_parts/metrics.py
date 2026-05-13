"""
ZENIC-AGENTS — Shared Memory Bus: Bus Metrics.

Performance counters for the shared memory bus. Uses simple integer
counters with a threading Lock for correctness. Minor races are
acceptable for observability data.
"""

import threading
from typing import Any, Dict


class BusMetrics:
    """Performance counters for the shared memory bus.

    Uses simple integer counters with a threading Lock for correctness.
    Minor races are acceptable for observability data.

    Tracks:
        - Per-agent: messages_sent, messages_received, total_latency_us
        - Global: total_throughput, buffer_utilization, db_flush_count
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Per-agent counters
        self._agent_sent: Dict[str, int] = {}
        self._agent_received: Dict[str, int] = {}
        self._agent_latency_us: Dict[str, float] = {}
        # Global counters
        self.total_throughput: int = 0
        self.db_flush_count: int = 0

    def record_send(self, agent_id: str, latency_us: float = 0.0) -> None:
        """Record a message sent by *agent_id*."""
        with self._lock:
            self._agent_sent[agent_id] = self._agent_sent.get(agent_id, 0) + 1
            self._agent_latency_us[agent_id] = (
                self._agent_latency_us.get(agent_id, 0.0) + latency_us
            )
            self.total_throughput += 1

    def record_receive(self, agent_id: str) -> None:
        """Record a message received by *agent_id*."""
        with self._lock:
            self._agent_received[agent_id] = (
                self._agent_received.get(agent_id, 0) + 1
            )

    def record_flush(self) -> None:
        """Record a database flush cycle."""
        with self._lock:
            self.db_flush_count += 1

    def snapshot(self, buffer_utilization: float = 0.0) -> Dict[str, Any]:
        """Return a point-in-time metrics snapshot."""
        with self._lock:
            per_agent: Dict[str, Dict[str, Any]] = {}
            all_agents = set(self._agent_sent) | set(self._agent_received)
            for aid in all_agents:
                sent = self._agent_sent.get(aid, 0)
                received = self._agent_received.get(aid, 0)
                total_lat = self._agent_latency_us.get(aid, 0.0)
                avg_lat = (total_lat / sent) if sent > 0 else 0.0
                per_agent[aid] = {
                    "messages_sent": sent,
                    "messages_received": received,
                    "avg_latency_us": round(avg_lat, 2),
                }
            return {
                "total_throughput": self.total_throughput,
                "buffer_utilization": round(buffer_utilization, 4),
                "db_flush_count": self.db_flush_count,
                "per_agent": per_agent,
            }
