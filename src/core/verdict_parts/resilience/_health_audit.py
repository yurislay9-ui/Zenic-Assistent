"""Verdict Resilience - Health Monitor & Auditor."""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ._types import VerdictCircuitState
from ._circuit_breaker import VerdictHealthSnapshot

logger = logging.getLogger("zenic_agents.verdict_parts.resilience")


class VerdictHealthMonitor:
    """
    Monitors the health of the LLM for verdict operations.

    Tracks:
      - Latency statistics
      - Success/failure rates
      - Timeout rates
      - Ambiguous response rates
      - Auto-disable when health is critically low

    The health monitor uses a sliding window of recent calls
    to determine if the LLM is reliable enough for verdicts.
    """

    def __init__(self, window_size: int = 50, unhealthy_threshold: float = 0.3):
        """
        Args:
            window_size: Number of recent calls to track.
            unhealthy_threshold: Success rate below this = unhealthy.
        """
        self._window_size = window_size
        self._unhealthy_threshold = unhealthy_threshold

        # Sliding window of call results
        self._results: deque = deque(maxlen=window_size)

        # Counters
        self._total_calls = 0
        self._total_successes = 0
        self._total_failures = 0
        self._total_timeouts = 0
        self._total_ambiguous = 0

        # Latency tracking
        self._total_latency = 0.0
        self._last_call_time: Optional[float] = None

        self._lock = threading.RLock()

    def record_call(self, success: bool, latency_s: float,
                    was_timeout: bool = False, was_ambiguous: bool = False) -> None:
        """Record the result of an LLM call."""
        with self._lock:
            self._total_calls += 1
            self._total_latency += latency_s
            self._last_call_time = time.monotonic()

            if success:
                self._total_successes += 1
            else:
                self._total_failures += 1

            if was_timeout:
                self._total_timeouts += 1
            if was_ambiguous:
                self._total_ambiguous += 1

            self._results.append({
                "success": success,
                "latency": latency_s,
                "timeout": was_timeout,
                "ambiguous": was_ambiguous,
                "time": time.monotonic(),
            })

    @property
    def is_healthy(self) -> bool:
        """Check if the LLM is healthy enough for verdict calls."""
        return self.snapshot.is_healthy

    @property
    def snapshot(self) -> VerdictHealthSnapshot:
        """Get a health snapshot."""
        with self._lock:
            # Calculate success rate from sliding window
            if not self._results:
                return VerdictHealthSnapshot(
                    is_healthy=True,  # No data = assume healthy
                    avg_latency_s=0.0,
                    success_rate=1.0,
                    total_calls=0,
                    total_failures=0,
                    total_timeouts=0,
                    total_ambiguous=0,
                    last_call_time=None,
                    circuit_breaker_state="unknown",
                )

            recent_successes = sum(1 for r in self._results if r["success"])
            success_rate = recent_successes / len(self._results)
            avg_latency = sum(r["latency"] for r in self._results) / max(len(self._results), 1)

            return VerdictHealthSnapshot(
                is_healthy=success_rate >= self._unhealthy_threshold,
                avg_latency_s=avg_latency,
                success_rate=success_rate,
                total_calls=self._total_calls,
                total_failures=self._total_failures,
                total_timeouts=self._total_timeouts,
                total_ambiguous=self._total_ambiguous,
                last_call_time=self._last_call_time,
                circuit_breaker_state="monitored",
            )

    @property
    def stats(self) -> Dict[str, Any]:
        """Health statistics."""
        snap = self.snapshot
        return {
            "is_healthy": snap.is_healthy,
            "success_rate": snap.success_rate,
            "avg_latency_s": snap.avg_latency_s,
            "total_calls": snap.total_calls,
            "total_failures": snap.total_failures,
            "total_timeouts": snap.total_timeouts,
            "total_ambiguous": snap.total_ambiguous,
        }


# ============================================================
#  VERDICT AUDITOR
# ============================================================

@dataclass
class VerdictAuditEntry:
    """Single audit entry for a verdict decision."""
    timestamp: float
    question: str
    verdict: str                  # YES or NO
    source: str                   # llm, consensus, fallback
    llm_used: bool
    confidence: float
    latency_ms: int
    retry_count: int
    evidence_for_count: int
    evidence_against_count: int
    consensus_score: float
    circuit_breaker_state: str = ""
    was_timeout: bool = False
    was_ambiguous: bool = False
    raw_llm_response: str = ""


class VerdictAuditor:
    """
    Auditor for the verdict system.

    Mantiene un buffer circular de las últimas N decisiones de veredicto
    para permitir análisis post-mortem y detección de patrones de fallo.

    El buffer es circular para limitar uso de memoria (< 1MB).
    """

    def __init__(self, max_entries: int = 100):
        """
        Args:
            max_entries: Maximum audit entries to keep (circular buffer).
        """
        self._entries: deque = deque(maxlen=max_entries)
        # SECURITY: Use RLock instead of Lock to prevent deadlock when
        # stats property acquires the lock and then calls
        # get_failure_pattern() which also acquires the same lock.
        self._lock = threading.RLock()

    def record(self, entry: VerdictAuditEntry) -> None:
        """Record a verdict audit entry."""
        with self._lock:
            self._entries.append(entry)

    def get_recent(self, count: int = 20) -> List[VerdictAuditEntry]:
        """Get the N most recent audit entries."""
        with self._lock:
            return list(self._entries)[-count:]

    def get_failure_pattern(self) -> Dict[str, Any]:
        """
        Analyze recent entries for failure patterns.

        Returns:
            Dictionary with pattern analysis.
        """
        with self._lock:
            if not self._entries:
                return {"pattern": "no_data", "risk": "unknown"}

            recent = list(self._entries)[-50:]  # Last 50

            # Count by source
            source_counts: Dict[str, int] = {}
            timeout_count = 0
            ambiguous_count = 0
            llm_failure_streak = 0
            max_llm_failure_streak = 0
            current_streak = 0

            for entry in recent:
                source_counts[entry.source] = source_counts.get(entry.source, 0) + 1
                if entry.was_timeout:
                    timeout_count += 1
                if entry.was_ambiguous:
                    ambiguous_count += 1

                # Track LLM failure streaks
                if entry.llm_used and entry.source == "fallback":
                    current_streak += 1
                    max_llm_failure_streak = max(max_llm_failure_streak, current_streak)
                else:
                    current_streak = 0

            # Detect patterns
            total = len(recent)
            fallback_rate = source_counts.get("fallback", 0) / total
            timeout_rate = timeout_count / total

            risk = "low"
            if fallback_rate > 0.5:
                risk = "high"
            elif fallback_rate > 0.3:
                risk = "medium"

            pattern = "healthy"
            if max_llm_failure_streak >= 5:
                pattern = "llm_consistently_failing"
            elif timeout_rate > 0.3:
                pattern = "frequent_timeouts"
            elif ambiguous_count > total * 0.2:
                pattern = "ambiguous_responses"
            elif fallback_rate > 0.5:
                pattern = "excessive_fallback"

            return {
                "pattern": pattern,
                "risk": risk,
                "total_entries": total,
                "source_distribution": source_counts,
                "timeout_rate": timeout_rate,
                "fallback_rate": fallback_rate,
                "max_llm_failure_streak": max_llm_failure_streak,
                "ambiguous_rate": ambiguous_count / total if total else 0,
            }

    @property
    def stats(self) -> Dict[str, Any]:
        """Audit statistics."""
        with self._lock:
            total = len(self._entries)
            if total == 0:
                return {"total_entries": 0, "pattern_analysis": "no_data"}

            pattern = self.get_failure_pattern()
            yes_count = sum(1 for e in self._entries if e.verdict == "YES")
            no_count = sum(1 for e in self._entries if e.verdict == "NO")

            return {
                "total_entries": total,
                "yes_count": yes_count,
                "no_count": no_count,
                "yes_rate": yes_count / total,
                "no_rate": no_count / total,
                "pattern_analysis": pattern,
            }


# ============================================================
#  VERDICT RESILIENCE ORCHESTRATOR
# ============================================================

