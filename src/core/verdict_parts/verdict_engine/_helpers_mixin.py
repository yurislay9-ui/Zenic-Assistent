"""VerdictEngine - Helpers Mixin."""

import re
import logging
import time
from typing import Any, Dict, List, Optional

try:
    from ..resilience import VerdictAuditEntry
    _AUDIT_AVAILABLE = True
except ImportError:
    _AUDIT_AVAILABLE = False

from ..types import Verdict, Evidence, VerdictInput, VerdictOutput, ConsensusResult

logger = logging.getLogger("zenic_agents.verdict_parts.verdict_engine")


class VerdictHelpersMixin:
    """Mixin providing resilience helpers, LLM call, parsing, and formatting."""


    # ================================================================
    #  INTERNAL: Resilience helpers
    # ================================================================

    def _compute_retry_delay(self, attempt: int) -> float:
        """Compute delay for retry with exponential backoff + jitter."""
        if self._resilience:
            return self._resilience.retry_config.compute_delay(attempt)
        import random
        delay = 1.0 * (2 ** (attempt - 1))
        delay = min(delay, 10.0)
        delay += random.uniform(0, 0.3 * delay)
        return delay

    def _record_success(self, latency_s: float, was_ambiguous: bool = False) -> None:
        """Record success to resilience systems."""
        if self._resilience:
            self._resilience.record_success(latency_s, was_ambiguous)

    def _record_failure(self, latency_s: float, was_timeout: bool = False,
                         was_ambiguous: bool = False) -> None:
        """Record failure to resilience systems."""
        if self._resilience:
            self._resilience.record_failure(
                latency_s, was_timeout=was_timeout, was_ambiguous=was_ambiguous
            )

    def _audit_result(self, question: str, verdict: str, source: str,
                       llm_used: bool, confidence: float, latency_ms: int,
                       retry_count: int, evidence_for_count: int,
                       evidence_against_count: int, consensus_score: float,
                       was_timeout: bool = False, was_ambiguous: bool = False,
                       circuit_breaker_state: str = "",
                       raw_response: str = "") -> None:
        """Record result in audit log."""
        if self._resilience and _AUDIT_AVAILABLE:
            entry = VerdictAuditEntry(
                timestamp=time.time(),
                question=question[:200],
                verdict=verdict,
                source=source,
                llm_used=llm_used,
                confidence=confidence,
                latency_ms=latency_ms,
                retry_count=retry_count,
                evidence_for_count=evidence_for_count,
                evidence_against_count=evidence_against_count,
                consensus_score=consensus_score,
                circuit_breaker_state=circuit_breaker_state or (
                    self._resilience.circuit_breaker.state.value
                ),
                was_timeout=was_timeout,
                was_ambiguous=was_ambiguous,
                raw_llm_response=raw_response[:100],
            )
            self._resilience.audit_verdict(entry)

    # ================================================================
    #  INTERNAL: LLM call and parsing
    # ================================================================

    def _call_llm_safe(self, prompt: str, max_tokens: int) -> Optional[str]:
        """Llama al LLM de forma segura. No lanza excepciones."""
        try:
            return self._mini_ai._call_llm(
                system_prompt="You are a binary decision maker. Reply with ONLY one word: YES or NO. Never explain. Never add anything else.",
                user_prompt=prompt,
                max_tokens=max_tokens,
            )
        except Exception as e:
            logger.warning(f"VerdictEngine: Safe LLM call failed: {e}")
            return None

    def _parse_verdict(self, response: str) -> Optional[Verdict]:
        """
        Parsea la respuesta del LLM. Solo acepta YES o NO.

        Reglas estrictas:
          - "YES" → Verdict.YES
          - "NO" → Verdict.NO
          - Cualquier otra cosa → None (cuenta como NO en el caller)
          - Case insensitive
          - Solo la primera palabra de la respuesta
        """
        if not response:
            return None

        # Limpiar thinking blocks de Qwen3
        clean = response.strip()
        think_match = re.search(r'</think\s*>(.*)', clean, re.DOTALL)
        if think_match:
            clean = think_match.group(1).strip()

        # Tomar solo la primera palabra
        first_word = clean.split()[0].upper() if clean.split() else ""

        # Solo aceptar YES o NO
        if first_word == "YES":
            return Verdict.YES
        elif first_word == "NO":
            return Verdict.NO
        # SECURITY: Removed substring fallback — "YESTERDAY"→YES was possible
        # Only exact matches are accepted. Any ambiguity → None → treated as NO.

        # Cualquier otra cosa = ambiguo = None (se convierte en NO)
        logger.warning(
            f"VerdictEngine: Ambiguous LLM response: '{response[:50]}'. Defaulting to NO."
        )
        return None

    # ================================================================
    #  INTERNAL: Formatting helpers
    # ================================================================

    def _format_evidence(self, evidence: List[Evidence]) -> str:
        """Formatea evidencia para incluir en el prompt del LLM."""
        if not evidence:
            return "None"
        parts = []
        for e in evidence[:3]:  # Max 3 items
            parts.append(f"[{e.source}] {e.detail} (weight={e.weight:.1f})")
        return "; ".join(parts)

    def _build_evidence_summary(self, consensus: ConsensusResult) -> str:
        """Construye un resumen de la evidencia del consenso."""
        total_for = len(consensus.evidence_for)
        total_against = len(consensus.evidence_against)
        return (
            f"Consensus: {consensus.verdict.value} "
            f"(score={consensus.score:.2f}, "
            f"confidence={consensus.confidence.value}, "
            f"for={total_for}, against={total_against}, "
            f"signals={consensus.signals_count})"
        )

    def _build_evidence_summary_from_input(self, input_data: VerdictInput) -> str:
        """Construye resumen de evidencia desde VerdictInput."""
        return (
            f"Evidence: for={len(input_data.evidence_for)}, "
            f"against={len(input_data.evidence_against)}, "
            f"score={input_data.consensus_score:.2f}"
        )

    def _build_context_summary(self, text: str, code: str,
                                pipeline_results: Dict[str, Any]) -> str:
        """Construye resumen de contexto para el prompt."""
        parts = []
        if text:
            parts.append(f"Input: {text[:100]}")
        if code:
            parts.append(f"Code length: {len(code)} chars")
        classify = pipeline_results.get("classify")
        if classify and classify.success:
            parts.append(f"Classification: {classify.result}")
        return " | ".join(parts) if parts else "No additional context"
