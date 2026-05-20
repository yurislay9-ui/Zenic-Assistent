"""Stats and lifecycle mixin for VerdictEngine."""

import logging
from typing import Any, Dict, List

from ..types import VerdictOutput
from ._config import VERDICT_CONSENSUS_ATTEMPTS, VERDICT_MAX_RETRIES

try:
    from ..resilience import (
        VerdictCircuitBreaker,
        VerdictRetryConfig,
        VerdictHealthMonitor,
        VerdictAuditor,
        VerdictAuditEntry,
        VerdictResilienceOrchestrator,
    )
    _RESILIENCE_AVAILABLE = True
except ImportError:
    _RESILIENCE_AVAILABLE = False

logger = logging.getLogger("zenic_agents.verdict_parts.verdict_engine")


class VerdictStatsMixin:
    """Mixin providing stats, health, and lifecycle methods for VerdictEngine."""

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del VerdictEngine con resiliencia."""
        with self._stats_lock:
            total_verdicts = self._total_verdicts
            llm_verdicts = self._llm_verdicts
            consensus_verdicts = self._consensus_verdicts
            low_confidence_verdicts = self._low_confidence_verdicts
            fallback_verdicts = self._fallback_verdicts
            yes_count = self._yes_count
            no_count = self._no_count
            total_time = self._total_time
        total = max(total_verdicts, 1)
        base_stats = {
            "total_verdicts": total_verdicts,
            "llm_verdicts": llm_verdicts,
            "consensus_verdicts": consensus_verdicts,
            "low_confidence_verdicts": low_confidence_verdicts,
            "fallback_verdicts": fallback_verdicts,
            "yes_count": yes_count,
            "no_count": no_count,
            "llm_rate": llm_verdicts / total,
            "consensus_rate": consensus_verdicts / total,
            "low_confidence_rate": low_confidence_verdicts / total,
            "fallback_rate": fallback_verdicts / total,
            "yes_rate": yes_count / total,
            "no_rate": no_count / total,
            "avg_time_s": total_time / total,
            "llm_available": self._mini_ai is not None and self._mini_ai.is_loaded,
            "consensus_attempts": VERDICT_CONSENSUS_ATTEMPTS,
            "max_retries": VERDICT_MAX_RETRIES,
        }
        if self._resilience:
            base_stats["resilience"] = self._resilience.stats
        return base_stats

    @property
    def health(self) -> Dict[str, Any]:
        """Health status of the verdict system."""
        if self._resilience:
            snap = self._resilience.health_snapshot
            return {
                "is_healthy": snap.is_healthy,
                "success_rate": snap.success_rate,
                "avg_latency_s": snap.avg_latency_s,
                "circuit_breaker_state": snap.circuit_breaker_state,
            }
        return {
            "is_healthy": self._mini_ai is not None and self._mini_ai.is_loaded,
            "success_rate": "unknown",
            "avg_latency_s": "unknown",
            "circuit_breaker_state": "not_configured",
        }

    def update_engines(self, mini_ai=None, semantic_engine=None,
                       smart_memory=None, memory_chip=None) -> None:
        """Actualiza las referencias a los motores."""
        if mini_ai is not None:
            self._mini_ai = mini_ai
        if semantic_engine is not None:
            self._semantic = semantic_engine
        if smart_memory is not None:
            self._memory = smart_memory
        if memory_chip is not None:
            self._memory_chip = memory_chip
            # Also inject into the pipeline
            self._pipeline.set_memory_chip(memory_chip)

        logger.info(
            f"VerdictEngine: Updated engines - "
            f"LLM={'available' if self._mini_ai and self._mini_ai.is_loaded else 'not available'}"
        )

    def reset_circuit_breaker(self) -> None:
        """Reset the circuit breaker to CLOSED state."""
        if self._resilience:
            self._resilience.circuit_breaker.reset()
            logger.info("VerdictEngine: Circuit breaker reset to CLOSED")

    def get_audit_trail(self, count: int = 20) -> List[Dict[str, Any]]:
        """Get recent audit entries as dictionaries."""
        if self._resilience and _RESILIENCE_AVAILABLE:
            entries = self._resilience.auditor.get_recent(count)
            return [
                {
                    "timestamp": e.timestamp,
                    "question": e.question,
                    "verdict": e.verdict,
                    "source": e.source,
                    "llm_used": e.llm_used,
                    "confidence": e.confidence,
                    "latency_ms": e.latency_ms,
                    "circuit_breaker_state": e.circuit_breaker_state,
                }
                for e in entries
            ]
        return []

    def get_failure_pattern(self) -> Dict[str, Any]:
        """Analyze recent verdicts for failure patterns."""
        if self._resilience:
            return self._resilience.auditor.get_failure_pattern()
        return {"pattern": "no_data", "risk": "unknown"}
