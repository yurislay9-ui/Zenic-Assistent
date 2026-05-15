"""
BaseAgent for v18 Single-Responsibility Architecture.

Every agent inherits from BaseAgent and implements EXACTLY ONE function.
All agents are deterministic by default. Only VerdictEngine uses AI.

INVARIANTS:
  1. No agent may call the LLM directly.
  2. Every agent MUST have a deterministic execute() method.
  3. Every agent call is wrapped with circuit breaker + retry + bulkhead.
  4. Every agent call is audited.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Generic, Optional, TypeVar

from .circuit_breaker import CircuitBreakerManager
from .retry import AgentRetryConfig, with_agent_retry
from .bulkhead import AgentBulkhead, BulkheadManager, BulkheadFullError
from .health_monitor import GlobalHealthMonitor
from .audit_logger import AuditLogger, AuditEntry

T = TypeVar("T")


class BaseAgent(Generic[T]):
    """
    Abstract base class for all v18 agents.

    Each agent has EXACTLY ONE responsibility, implemented in execute().
    All resilience patterns are applied automatically.
    """

    def __init__(
        self,
        name: str,
        circuit_breaker_manager: Optional[CircuitBreakerManager] = None,
        bulkhead_manager: Optional[BulkheadManager] = None,
        health_monitor: Optional[GlobalHealthMonitor] = None,
        audit_logger: Optional[AuditLogger] = None,
        retry_config: Optional[AgentRetryConfig] = None,
    ) -> None:
        self.name = name
        self._cb_manager = circuit_breaker_manager or CircuitBreakerManager()
        self._bulkhead_manager = bulkhead_manager or BulkheadManager()
        self._health_monitor = health_monitor or GlobalHealthMonitor()
        self._audit_logger = audit_logger or AuditLogger()
        self._retry_config = retry_config or AgentRetryConfig()

        # Thread-safe stats
        self._stats_lock = threading.Lock()
        self._call_count = 0
        self._success_count = 0
        self._fallback_count = 0
        self._total_duration_ms = 0.0
        self._last_error = ""

    def execute(self, input_data: Any) -> T:
        """
        The ONE function this agent performs.

        MUST be overridden by every concrete agent.
        MUST be deterministic (no AI calls).
        MUST always return a valid result (never raises).
        """
        raise NotImplementedError(
            f"Agent {self.name} must implement execute() with exactly ONE responsibility"
        )

    def fallback(self, input_data: Any) -> T:
        """
        Deterministic fallback when execute() fails.
        MUST be overridden. MUST always succeed.
        """
        raise NotImplementedError(
            f"Agent {self.name} must implement fallback()"
        )

    def run(self, input_data: Any) -> dict[str, Any]:
        """
        Run the agent with full resilience:
        1. Check circuit breaker
        2. Acquire bulkhead slot
        3. Execute with retry
        4. Fallback on failure
        5. Audit the result
        6. Report to health monitor
        """
        start_time = time.monotonic()
        result = None
        source = "deterministic"
        retry_count = 0
        error = ""

        # 1. Circuit breaker check
        if not self._cb_manager.can_call(self.name):
            source = "circuit_open_fallback"
            try:
                result = self.fallback(input_data)
            except Exception as e:
                error = str(e)
            self._record_run(start_time, source, result is not None, error, retry_count)
            return self._format_result(result, source, start_time, retry_count)

        # 2. Bulkhead
        bulkhead = self._bulkhead_manager.get_bulkhead(self.name)
        if not bulkhead.acquire(timeout=5.0):
            source = "bulkhead_fallback"
            try:
                result = self.fallback(input_data)
            except Exception as e:
                error = str(e)
            self._record_run(start_time, source, result is not None, error, retry_count)
            return self._format_result(result, source, start_time, retry_count)

        try:
            # 3. Execute with retry
            for attempt in range(1, self._retry_config.max_attempts + 1):
                try:
                    result = self.execute(input_data)
                    source = "deterministic"
                    break
                except Exception as e:
                    error = str(e)
                    retry_count = attempt
                    if attempt < self._retry_config.max_attempts:
                        delay = self._retry_config.compute_delay(attempt)
                        time.sleep(delay)
            else:
                # All retries exhausted → fallback
                try:
                    result = self.fallback(input_data)
                    source = "fallback"
                    error = ""
                except Exception as e:
                    error = str(e)
                    source = "error"

        finally:
            bulkhead.release()

        # 5. Record success/failure for circuit breaker
        # Three categories:
        #   - Success: execute() completed → CB success
        #   - Degraded: fallback/circuit_open/bulkhead → NOT a CB failure
        #     (fallback is a successful recovery; CB/bulkhead fallback is
        #      caused by resilience itself, not agent failure)
        #   - Hard failure: execute() raised after all retries → CB failure
        if source == "deterministic":
            self._cb_manager.record_success(self.name)
            success = True
        elif source in ("error",):
            self._cb_manager.record_failure(self.name)
            success = False
        else:
            # Degraded success: fallback, circuit_open_fallback, bulkhead_fallback
            # Do NOT record as CB failure — prevents death spiral
            success = True  # Fallback is a successful recovery

        # 6. Audit + Health
        self._record_run(start_time, source, success, error, retry_count)

        return self._format_result(result, source, start_time, retry_count)

    def _record_run(
        self,
        start_time: float,
        source: str,
        success: bool,
        error: str,
        retry_count: int,
    ) -> None:
        """Record stats, health, and audit."""
        duration_ms = (time.monotonic() - start_time) * 1000

        with self._stats_lock:
            self._call_count += 1
            if success:
                self._success_count += 1
            if "fallback" in source:
                self._fallback_count += 1
            self._total_duration_ms += duration_ms
            if error:
                self._last_error = error

        # Health monitor
        self._health_monitor.record_call(
            agent_name=self.name,
            success=success,
            latency_s=duration_ms / 1000,
            was_timeout="timeout" in error.lower(),
        )

        # Audit
        cb_state = self._cb_manager.get_breaker(self.name).state.value
        self._audit_logger.record(AuditEntry(
            agent=self.name,
            source=source,
            duration_ms=duration_ms,
            retry_count=retry_count,
            circuit_breaker_state=cb_state,
            evidence_summary=error[:200] if error else "",
        ))

    def _format_result(
        self,
        result: Any,
        source: str,
        start_time: float,
        retry_count: int,
    ) -> dict[str, Any]:
        """Format result into standard envelope."""
        duration_ms = (time.monotonic() - start_time) * 1000
        return {
            "success": result is not None,
            "data": result,
            "source": source,
            "duration_ms": duration_ms,
            "retry_count": retry_count,
            "agent": self.name,
        }

    @property
    def stats(self) -> dict[str, Any]:
        with self._stats_lock:
            avg_duration = (
                self._total_duration_ms / self._call_count
                if self._call_count > 0
                else 0.0
            )
            success_rate = (
                self._success_count / self._call_count
                if self._call_count > 0
                else 1.0
            )
            return {
                "name": self.name,
                "call_count": self._call_count,
                "success_count": self._success_count,
                "fallback_count": self._fallback_count,
                "success_rate": success_rate,
                "avg_duration_ms": avg_duration,
                "last_error": self._last_error,
            }
