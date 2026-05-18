"""Verdict Resilience - Orchestrator."""

import logging
import time
from typing import Any, Dict, Optional

from ._types import VerdictCircuitState
from ._circuit_breaker import VerdictCircuitBreaker, VerdictRetryConfig, VerdictHealthSnapshot
from ._health_audit import VerdictHealthMonitor, VerdictAuditor, VerdictAuditEntry

logger = logging.getLogger("zenic_agents.verdict_parts.resilience")


class VerdictResilienceOrchestrator:
    """
    Orchestrates all resilience patterns for the verdict system.

    Combines:
      - Circuit Breaker: Prevents calls when LLM is down
      - Health Monitor: Tracks LLM health metrics
      - Auditor: Records decisions for analysis
      - Retry Policy: Manages retry behavior

    Usage:
        resilience = VerdictResilienceOrchestrator()

        # Before calling LLM
        if resilience.can_call_llm():
            result = call_llm(...)
            resilience.record_result(result)

        # Get health status
        health = resilience.health_snapshot
    """

    def __init__(
        self,
        circuit_breaker: Optional[VerdictCircuitBreaker] = None,
        health_monitor: Optional[VerdictHealthMonitor] = None,
        auditor: Optional[VerdictAuditor] = None,
        retry_config: Optional[VerdictRetryConfig] = None,
    ):
        self.circuit_breaker = circuit_breaker or VerdictCircuitBreaker()
        self.health_monitor = health_monitor or VerdictHealthMonitor()
        self.auditor = auditor or VerdictAuditor()
        self.retry_config = retry_config or VerdictRetryConfig()

    def can_call_llm(self) -> bool:
        """
        Check if an LLM call is allowed.

        Returns False if:
          - Circuit breaker is OPEN
          - Health monitor detects critical failure
        """
        if not self.circuit_breaker.can_call():
            logger.debug("VerdictResilience: Circuit breaker OPEN, LLM call rejected")
            return False

        if not self.health_monitor.is_healthy:
            # Allow through circuit breaker (it has its own logic)
            # but log the health warning
            snap = self.health_monitor.snapshot
            logger.warning(
                f"VerdictResilience: LLM health is LOW "
                f"(success_rate={snap.success_rate:.2f}), "
                f"proceeding with caution"
            )

        return True

    def record_success(self, latency_s: float, was_ambiguous: bool = False) -> None:
        """Record a successful LLM verdict call."""
        self.circuit_breaker.record_success()
        self.health_monitor.record_call(
            success=True, latency_s=latency_s, was_ambiguous=was_ambiguous
        )

    def record_failure(self, latency_s: float, was_timeout: bool = False,
                       was_ambiguous: bool = False) -> None:
        """Record a failed LLM verdict call."""
        self.circuit_breaker.record_failure()
        self.health_monitor.record_call(
            success=False, latency_s=latency_s,
            was_timeout=was_timeout, was_ambiguous=was_ambiguous
        )

    def audit_verdict(self, entry: VerdictAuditEntry) -> None:
        """Record a verdict in the audit log."""
        self.auditor.record(entry)

    @property
    def health_snapshot(self) -> VerdictHealthSnapshot:
        """Current health snapshot."""
        snap = self.health_monitor.snapshot
        return VerdictHealthSnapshot(
            is_healthy=snap.is_healthy,
            avg_latency_s=snap.avg_latency_s,
            success_rate=snap.success_rate,
            total_calls=snap.total_calls,
            total_failures=snap.total_failures,
            total_timeouts=snap.total_timeouts,
            total_ambiguous=snap.total_ambiguous,
            last_call_time=snap.last_call_time,
            circuit_breaker_state=self.circuit_breaker.state.value,
        )

    @property
    def stats(self) -> Dict[str, Any]:
        """Comprehensive resilience statistics."""
        return {
            "circuit_breaker": self.circuit_breaker.stats,
            "health": self.health_monitor.stats,
            "audit": self.auditor.stats,
            "retry_config": {
                "max_attempts": self.retry_config.max_attempts,
                "base_delay": self.retry_config.base_delay,
                "timeout_per_attempt": self.retry_config.timeout_per_attempt,
            },
        }
