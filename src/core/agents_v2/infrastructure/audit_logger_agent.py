"""
A46 AuditLoggerAgent — SINGLE RESPONSIBILITY: Log all agent decisions for post-mortem analysis.

Wraps AuditLogger as a BaseAgent so it can participate in the agent pipeline.
Provides recording, querying, and failure pattern analysis.

Ported from:
  - resilience/audit_logger.py (AuditLogger)
"""

from __future__ import annotations

import time
from typing import Any, Optional

from ..resilience import BaseAgent, AuditLogger, AuditEntry
from ..schemas import AgentResult


class AuditLoggerAgent(BaseAgent[AgentResult]):
    """
    A46: Log all agent decisions for post-mortem analysis.

    Single Responsibility: Audit logging ONLY.
    Method: Record entries and query/analyze audit trail.
    Fallback: Return empty result (logging failure is non-fatal).
    """

    def __init__(
        self,
        audit_logger: Optional[AuditLogger] = None,
        **kwargs,
    ) -> None:
        super().__init__(name="A46_AuditLogger", **kwargs)
        self._logger = audit_logger or AuditLogger()

    def execute(self, input_data: Any) -> AgentResult:
        """
        Execute audit action.

        input_data must be a dict with:
          - 'action': "record" | "query" | "analyze" | "stats"
          - For "record": 'entry' key with AuditEntry or dict
          - For "query": 'agent_name' (optional), 'count' (optional, default 20)
          - For "analyze": 'agent_name' (optional)
          - For "stats": no additional keys needed
        """
        if not isinstance(input_data, dict):
            return self.fallback(input_data)

        action = input_data.get("action", "stats")

        if action == "record":
            return self._record(input_data)
        elif action == "query":
            return self._query(input_data)
        elif action == "analyze":
            return self._analyze(input_data)
        elif action == "stats":
            return self._stats()
        else:
            return AgentResult(
                success=False,
                source="error",
                error=f"Unknown audit action: {action}",
            )

    def _record(self, input_data: dict) -> AgentResult:
        """Record an audit entry."""
        entry_data = input_data.get("entry", input_data)

        if isinstance(entry_data, AuditEntry):
            self._logger.record(entry_data)
        elif isinstance(entry_data, dict):
            entry = AuditEntry(
                agent=entry_data.get("agent", "unknown"),
                input_hash=entry_data.get("input_hash", ""),
                output_hash=entry_data.get("output_hash", ""),
                source=entry_data.get("source", "deterministic"),
                confidence=entry_data.get("confidence", 0.0),
                duration_ms=entry_data.get("duration_ms", 0.0),
                retry_count=entry_data.get("retry_count", 0),
                circuit_breaker_state=entry_data.get("circuit_breaker_state", "CLOSED"),
                evidence_summary=entry_data.get("evidence_summary", ""),
            )
            self._logger.record(entry)
        else:
            return AgentResult(
                success=False,
                source="error",
                error="Invalid entry format for audit record",
            )

        return AgentResult(
            success=True,
            source="deterministic",
        )

    def _query(self, input_data: dict) -> AgentResult:
        """Query recent audit entries."""
        agent_name = input_data.get("agent_name")
        count = input_data.get("count", 20)

        entries = self._logger.get_recent(agent_name, count)
        entry_dicts = [e.to_dict() for e in entries]

        return AgentResult(
            success=True,
            data=entry_dicts,
            source="deterministic",
        )

    def _analyze(self, input_data: dict) -> AgentResult:
        """Analyze audit trail for failure patterns."""
        agent_name = input_data.get("agent_name")
        pattern = self._logger.get_failure_pattern(agent_name)

        return AgentResult(
            success=True,
            data=pattern,
            source="deterministic",
        )

    def _stats(self) -> AgentResult:
        """Get audit logger stats."""
        return AgentResult(
            success=True,
            data=self._logger.stats,
            source="deterministic",
        )

    # ──────────────────────────────────────────────────────────
    # CONVENIENCE METHODS (for direct use by AgentRunner)
    # ──────────────────────────────────────────────────────────

    def record_decision(
        self,
        agent_name: str,
        source: str,
        duration_ms: float,
        retry_count: int = 0,
        circuit_breaker_state: str = "CLOSED",
        evidence_summary: str = "",
        input_data: Any = None,
        output_data: Any = None,
    ) -> None:
        """Record a decision with optional input/output hashing."""
        input_hash = AuditLogger.hash_data(input_data) if input_data else ""
        output_hash = AuditLogger.hash_data(output_data) if output_data else ""

        self._logger.record(AuditEntry(
            agent=agent_name,
            input_hash=input_hash,
            output_hash=output_hash,
            source=source,
            duration_ms=duration_ms,
            retry_count=retry_count,
            circuit_breaker_state=circuit_breaker_state,
            evidence_summary=evidence_summary[:200],
        ))

    def get_recent(self, agent_name: Optional[str] = None, count: int = 20) -> list[AuditEntry]:
        """Get recent entries directly."""
        return self._logger.get_recent(agent_name, count)

    def get_failure_pattern(self, agent_name: Optional[str] = None) -> dict[str, Any]:
        """Analyze failure patterns directly."""
        return self._logger.get_failure_pattern(agent_name)

    def fallback(self, input_data: Any) -> AgentResult:
        """Fallback: logging failure is non-fatal."""
        return AgentResult(
            success=True,
            source="fallback",
            data={},
        )
