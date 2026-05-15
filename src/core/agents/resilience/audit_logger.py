"""
Audit Logger for v18 agents.

Every agent decision is logged with full context.
Circular buffer to limit memory (<1MB total).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import deque
from typing import Any, Optional


class AuditEntry:
    """A single audit log entry."""

    __slots__ = (
        "timestamp", "agent", "input_hash", "output_hash",
        "source", "confidence", "duration_ms", "retry_count",
        "circuit_breaker_state", "evidence_summary",
    )

    def __init__(
        self,
        agent: str,
        input_hash: str = "",
        output_hash: str = "",
        source: str = "deterministic",
        confidence: float = 0.0,
        duration_ms: float = 0.0,
        retry_count: int = 0,
        circuit_breaker_state: str = "CLOSED",
        evidence_summary: str = "",
        timestamp: Optional[float] = None,
    ) -> None:
        self.timestamp = timestamp or time.monotonic()
        self.agent = agent
        self.input_hash = input_hash
        self.output_hash = output_hash
        self.source = source
        self.confidence = confidence
        self.duration_ms = duration_ms
        self.retry_count = retry_count
        self.circuit_breaker_state = circuit_breaker_state
        self.evidence_summary = evidence_summary

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "agent": self.agent,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "source": self.source,
            "confidence": self.confidence,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
            "circuit_breaker_state": self.circuit_breaker_state,
            "evidence_summary": self.evidence_summary,
        }


class AuditLogger:
    """
    Thread-safe circular audit buffer.

    Enables:
    - Post-mortem analysis of failures
    - Compliance auditing
    - Pattern detection
    - Performance regression detection
    """

    def __init__(self, max_entries: int = 200, total_max: int = 2000) -> None:
        self.max_entries = max_entries
        self.total_max = total_max

        self._per_agent: dict[str, deque] = {}
        self._global: deque = deque(maxlen=total_max)
        self._lock = threading.Lock()

    def record(self, entry: AuditEntry) -> None:
        """Record an audit entry."""
        with self._lock:
            # Per-agent circular buffer
            if entry.agent not in self._per_agent:
                self._per_agent[entry.agent] = deque(maxlen=self.max_entries)
            self._per_agent[entry.agent].append(entry)

            # Global buffer
            self._global.append(entry)

    def get_recent(self, agent_name: Optional[str] = None, count: int = 20) -> list[AuditEntry]:
        """Get recent entries, optionally filtered by agent."""
        with self._lock:
            if agent_name:
                entries = list(self._per_agent.get(agent_name, deque()))
            else:
                entries = list(self._global)
            return entries[-count:]

    def get_failure_pattern(self, agent_name: Optional[str] = None) -> dict[str, Any]:
        """Analyze audit log for failure patterns."""
        entries = self.get_recent(agent_name, count=100)
        if not entries:
            return {"pattern": "no_data", "risk_level": "low"}

        total = len(entries)
        failures = [e for e in entries if e.source in ("fallback", "error")]
        timeouts = [e for e in entries if "timeout" in e.evidence_summary.lower()]
        low_confidence = [e for e in entries if e.confidence < 0.3]

        failure_rate = len(failures) / total if total > 0 else 0
        timeout_rate = len(timeouts) / total if total > 0 else 0

        risk = "low"
        if failure_rate > 0.5 or timeout_rate > 0.3:
            risk = "high"
        elif failure_rate > 0.3 or timeout_rate > 0.1:
            risk = "medium"

        return {
            "total_entries": total,
            "failure_count": len(failures),
            "failure_rate": failure_rate,
            "timeout_count": len(timeouts),
            "timeout_rate": timeout_rate,
            "low_confidence_count": len(low_confidence),
            "llm_consistently_failing": failure_rate > 0.5,
            "frequent_timeouts": timeout_rate > 0.2,
            "risk_level": risk,
        }

    @property
    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "agents_tracked": len(self._per_agent),
                "total_entries": len(self._global),
                "per_agent_counts": {
                    name: len(entries) for name, entries in self._per_agent.items()
                },
            }

    @staticmethod
    def hash_data(data: Any) -> str:
        """Create deterministic hash of data for audit trail."""
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]
