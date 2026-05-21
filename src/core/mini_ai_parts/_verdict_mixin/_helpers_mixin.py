"""VerdictMixin helper methods: retry, recording, auditing, parsing, stats."""

import re
import time
import logging
from typing import Dict, Any, Optional

from ._constants import (
    VERDICT_BASE_DELAY,
    VERDICT_MAX_DELAY,
    VERDICT_MAX_RETRIES,
    VERDICT_SYSTEM_PROMPT,
    VERDICT_CONSENSUS_ATTEMPTS,
    _RESILIENCE_AVAILABLE,
)

from src.core.shared.deterministic import ControllableJitter
from src.core.verdict_engine_module import _validate_ai_verdict  # H-88: AI output validation

if _RESILIENCE_AVAILABLE:
    from ._constants import (  # noqa: F401 — conditional import
        VerdictAuditEntry,
    )

logger = logging.getLogger(__name__)


# Deterministic jitter for fallback retry (Phase 5 fix)
_fallback_jitter = ControllableJitter("mini_ai_verdict_helpers")


class VerdictHelpersMixin:
    """Helper methods for verdict: retry, recording, auditing, parsing, stats."""

    def _compute_retry_delay(self, attempt: int) -> float:
        """Compute delay for retry with exponential backoff + jitter."""
        if self._verdict_resilience:
            return self._verdict_resilience.retry_config.compute_delay(attempt)
        # Fallback delay calculation
        delay = VERDICT_BASE_DELAY * (2 ** (attempt - 1))
        delay = min(delay, VERDICT_MAX_DELAY)
        delay = _fallback_jitter.apply(delay, 0.3)
        return delay

    def _record_verdict_success(self, latency_s: float, was_yes: bool) -> None:
        """Record a successful verdict to resilience systems."""
        if self._verdict_resilience:
            self._verdict_resilience.record_success(latency_s, was_ambiguous=False)

    def _record_verdict_failure(self, latency_s: float,
                                 was_timeout: bool = False,
                                 was_ambiguous: bool = False) -> None:
        """Record a failed verdict to resilience systems."""
        if self._verdict_resilience:
            self._verdict_resilience.record_failure(
                latency_s, was_timeout=was_timeout, was_ambiguous=was_ambiguous
            )

    def _audit_verdict(self, question: str, verdict: str, source: str,
                        llm_used: bool, confidence: float, latency_ms: int,
                        retry_count: int, evidence_for: str = "",
                        evidence_against: str = "", consensus_score: float = 0.0,
                        was_timeout: bool = False, was_ambiguous: bool = False,
                        circuit_breaker_state: str = "",
                        raw_response: str = "") -> None:
        """Record verdict in the audit log."""
        if self._verdict_resilience and _RESILIENCE_AVAILABLE:
            entry = VerdictAuditEntry(
                timestamp=time.time(),
                question=question[:200],
                verdict=verdict,
                source=source,
                llm_used=llm_used,
                confidence=confidence,
                latency_ms=latency_ms,
                retry_count=retry_count,
                evidence_for_count=len(evidence_for) if evidence_for else 0,
                evidence_against_count=len(evidence_against) if evidence_against else 0,
                consensus_score=consensus_score,
                circuit_breaker_state=circuit_breaker_state or (
                    self._verdict_resilience.circuit_breaker.state.value
                ),
                was_timeout=was_timeout,
                was_ambiguous=was_ambiguous,
                raw_llm_response=raw_response[:100],  # Truncate for memory
            )
            self._verdict_resilience.audit_verdict(entry)

    def _verdict_llm_call(self, user_prompt: str) -> Optional[str]:
        """LLM call specific for verdicts.

        H-88: All AI output is validated through _validate_ai_verdict()
        to ensure strictly binary YES/NO responses.
        """
        try:
            raw = self._call_llm(
                system_prompt=VERDICT_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=10,  # VERDICT_MAX_TOKENS
            )
            if raw is None:
                return None
            # H-88: Validate AI output is strictly binary before passing to parser
            return _validate_ai_verdict(raw)
        except Exception as e:
            logger.warning(f"VerdictMixin: LLM call failed: {e}")
            return None

    @staticmethod
    def _parse_verdict_response(response: str) -> Optional[str]:
        """
        Parse the LLM response. Only accepts YES or NO.

        H-88: Strict parsing — NO substring matching.
        "YESTERDAY" → None, "NOTICE" → None.

        Rules:
          - "YES" → "YES"
          - "NO" → "NO"
          - Anything else → None (counts as NO in the caller)
        """
        if not response:
            return None

        # Clean Qwen3 thinking blocks
        clean = response.strip()
        think_match = re.search(r'</think\s*>(.*)', clean, re.DOTALL)
        if think_match:
            clean = think_match.group(1).strip()

        # Take only the first word
        first_word = clean.split()[0].upper() if clean.split() else ""

        # SECURITY (H-88): Only exact matches accepted. No substring fallback.
        # "YESTERDAY"→YES was possible with the old substring check.
        if first_word == "YES":
            return "YES"
        elif first_word == "NO":
            return "NO"

        # Ambiguous = None → converted to NO
        logger.warning(f"VerdictMixin: Ambiguous response: '{response[:50]}'")
        return None

    @property
    def verdict_stats(self) -> Dict[str, Any]:
        """Verdict statistics with resilience."""
        total = max(self._verdict_count, 1)
        base_stats: Dict[str, Any] = {
            "total_verdicts": self._verdict_count,
            "yes_count": self._verdict_yes,
            "no_count": self._verdict_no,
            "fallback_count": self._verdict_fallback,
            "yes_rate": self._verdict_yes / total,
            "no_rate": self._verdict_no / total,
            "fallback_rate": self._verdict_fallback / total,
            "llm_available": self.is_loaded,
            "consensus_attempts": VERDICT_CONSENSUS_ATTEMPTS,
            "max_retries": VERDICT_MAX_RETRIES,
        }
        if self._verdict_resilience:
            base_stats["resilience"] = self._verdict_resilience.stats
        return base_stats
