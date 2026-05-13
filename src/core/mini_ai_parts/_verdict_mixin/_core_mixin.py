"""VerdictMixin core methods: init, verdict entry point, prompt building."""

import time
import logging
import concurrent.futures
from typing import Dict, Any

from ._constants import (
    VERDICT_CONSENSUS_ATTEMPTS,
    VERDICT_MAX_RETRIES,
    VERDICT_BASE_DELAY,
    VERDICT_MAX_DELAY,
    VERDICT_TIMEOUT_S,
    VERDICT_SYSTEM_PROMPT,
    _RESILIENCE_AVAILABLE,
)

if _RESILIENCE_AVAILABLE:
    from ._constants import (  # noqa: F401 — re-export for sibling modules
        VerdictCircuitBreaker,
        VerdictRetryConfig,
        VerdictHealthMonitor,
        VerdictAuditor,
        VerdictAuditEntry,
        VerdictResilienceOrchestrator,
    )

logger = logging.getLogger(__name__)


class VerdictCoreMixin:
    """Core verdict methods: initialization, entry point, prompt construction."""

    def _init_verdict(self):
        """Initialize the verdict subsystem with resilience."""
        self._verdict_count = 0
        self._verdict_yes = 0
        self._verdict_no = 0
        self._verdict_fallback = 0
        self._verdict_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        # v17.1: Resilience patterns
        if _RESILIENCE_AVAILABLE:
            self._verdict_resilience = VerdictResilienceOrchestrator(
                circuit_breaker=VerdictCircuitBreaker(
                    name="verdict_llm",
                    failure_threshold=3,
                    recovery_timeout=60.0,
                    half_open_max_calls=1,
                    success_threshold=2,
                ),
                health_monitor=VerdictHealthMonitor(
                    window_size=50,
                    unhealthy_threshold=0.3,
                ),
                auditor=VerdictAuditor(max_entries=100),
                retry_config=VerdictRetryConfig(
                    max_attempts=VERDICT_MAX_RETRIES,
                    base_delay=VERDICT_BASE_DELAY,
                    max_delay=VERDICT_MAX_DELAY,
                    timeout_per_attempt=VERDICT_TIMEOUT_S,
                ),
            )
        else:
            self._verdict_resilience = None

        logger.info(
            f"VerdictMixin: Initialized with resilience="
            f"{_RESILIENCE_AVAILABLE}, "
            f"max_retries={VERDICT_MAX_RETRIES}, "
            f"consensus_attempts={VERDICT_CONSENSUS_ATTEMPTS}"
        )

    def verdict(self, question: str, context: str = "",
                evidence_for: str = "", evidence_against: str = "",
                consensus_hint: float = 0.0) -> Dict[str, Any]:
        """
        Ask the AI for a binary verdict: YES or NO.

        This is the ONLY method that should be used to interact with the AI.

        v17.1 Flow with resilience:
          1. Check Circuit Breaker → if OPEN, immediate fallback NO
          2. Check Health Monitor → if unhealthy, log warning
          3. Multi-attempt consensus: Ask N times
          4. Majority decides (threshold = 2 of 3)
          5. If all fail → fallback NO
          6. Audit result

        Args:
            question: The binary question to answer
            context: Additional context (summary, not raw input)
            evidence_for: Summary of evidence in favor
            evidence_against: Summary of evidence against
            consensus_hint: Consensus score (-1.0 to 1.0)

        Returns:
            Dict with: verdict ("YES"/"NO"), confidence, source, raw_response
        """
        self._verdict_count += 1
        start = time.time()

        if not self.is_loaded:
            self._verdict_fallback += 1
            self._verdict_no += 1
            self._audit_verdict(
                question, "NO", "fallback_no_model", False, 0.0,
                int((time.time() - start) * 1000), 0,
                evidence_for, evidence_against, consensus_hint
            )
            return {
                "verdict": "NO",
                "confidence": 0.0,
                "source": "fallback_no_model",
                "raw_response": "",
                "time_ms": 0,
                "retry_count": 0,
            }

        # v17.1: Check Circuit Breaker
        if self._verdict_resilience and not self._verdict_resilience.can_call_llm():
            self._verdict_fallback += 1
            self._verdict_no += 1
            elapsed_ms = int((time.time() - start) * 1000)
            self._audit_verdict(
                question, "NO", "fallback_circuit_open", False, 0.0,
                elapsed_ms, 0, evidence_for, evidence_against, consensus_hint,
                circuit_breaker_state="open"
            )
            return {
                "verdict": "NO",
                "confidence": 0.0,
                "source": "fallback_circuit_open",
                "raw_response": "",
                "time_ms": elapsed_ms,
                "retry_count": 0,
            }

        # Build user prompt with evidence
        user_prompt = self._build_verdict_prompt(
            question, context, evidence_for, evidence_against, consensus_hint
        )

        # v17.1: Multi-attempt consensus
        if VERDICT_CONSENSUS_ATTEMPTS > 1:
            result = self._verdict_multi_attempt(
                user_prompt, question, start, evidence_for, evidence_against, consensus_hint
            )
        else:
            result = self._verdict_single_attempt(
                user_prompt, question, start, evidence_for, evidence_against, consensus_hint
            )

        return result

    def _build_verdict_prompt(self, question: str, context: str,
                               evidence_for: str, evidence_against: str,
                               consensus_hint: float) -> str:
        """Build the prompt for the verdict."""
        user_parts = [f"Question: {question}"]
        if evidence_for:
            user_parts.append(f"Evidence FOR: {evidence_for[:200]}")
        if evidence_against:
            user_parts.append(f"Evidence AGAINST: {evidence_against[:200]}")
        if consensus_hint != 0.0:
            user_parts.append(f"Consensus score: {consensus_hint:.2f}")
        if context:
            user_parts.append(f"Context: {context[:200]}")
        return "\n".join(user_parts)

    def _ensure_verdict_executor(self):
        """Ensure _verdict_executor is available, creating it lazily if needed.

        FIX (v18.1): After unload_model() shuts down _verdict_executor and
        sets it to None, subsequent verdict calls would crash with
        AttributeError: 'NoneType' object has no attribute 'submit'.
        This method lazily recreates the executor, matching the pattern
        used by _call_llm() for self._executor.
        """
        if getattr(self, '_verdict_executor', None) is None:
            self._verdict_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
