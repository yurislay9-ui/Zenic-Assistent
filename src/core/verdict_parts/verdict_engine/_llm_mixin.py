"""VerdictEngine - LLM Request Mixin."""

import logging
import time
import concurrent.futures
from typing import Any, Dict, List, Optional

from ..types import Verdict, Evidence, VerdictInput, VerdictOutput, VerdictConfidence
from ._config import VERDICT_TIMEOUT_S, VERDICT_MAX_TOKENS, VERDICT_MAX_RETRIES, VERDICT_CONSENSUS_ATTEMPTS, VERDICT_CONSENSUS_THRESHOLD, VERDICT_PROMPT_TEMPLATE

logger = logging.getLogger("zenic_agents.verdict_parts.verdict_engine")


class VerdictLLMMixin:
    """Mixin providing LLM verdict request methods."""


    # ================================================================
    #  INTERNAL: LLM verdict request with full resilience
    # ================================================================

    def _request_llm_verdict(self, input_data: VerdictInput,
                              start_time: float) -> VerdictOutput:
        """
        Solicita un veredicto al LLM con resiliencia completa.

        v17.1 Flujo:
          1. Check Circuit Breaker → si OPEN, fallback NO inmediato
          2. Multi-attempt consensus (3 intentos, mayoría gana)
          3. Si majority clara → retornar
          4. Si no → Retry con exponential backoff (máx 3 rondas)
          5. Si todo falla → Fallback NO
          6. Auditar resultado
        """
        self._llm_verdicts += 1

        # v17.1: Check Circuit Breaker
        if self._resilience and not self._resilience.can_call_llm():
            elapsed = time.time() - start_time
            self._total_time += elapsed
            self._fallback_verdicts += 1
            self._no_count += 1

            evidence_summary = self._build_evidence_summary_from_input(input_data)

            logger.warning("VerdictEngine: Circuit breaker OPEN, using fallback NO")

            self._audit_result(
                input_data.question, "NO", "fallback_circuit_open",
                False, 0.0, int(elapsed * 1000), 0,
                len(input_data.evidence_for), len(input_data.evidence_against),
                input_data.consensus_score,
                circuit_breaker_state="open"
            )

            return VerdictOutput(
                verdict=Verdict.NO,
                confidence=0.0,
                source="fallback_circuit_open",
                evidence_summary=evidence_summary + " [CIRCUIT BREAKER OPEN]",
                llm_used=False,
                llm_raw_response="",
                retry_count=0,
            )

        # Build prompt
        evidence_for_str = self._format_evidence(input_data.evidence_for[:3])
        evidence_against_str = self._format_evidence(input_data.evidence_against[:3])

        prompt = VERDICT_PROMPT_TEMPLATE.format(
            evidence_for=evidence_for_str,
            evidence_against=evidence_against_str,
            score=input_data.consensus_score,
            question=input_data.question,
        )

        # v17.1: Multi-attempt consensus
        if VERDICT_CONSENSUS_ATTEMPTS > 1 and self._mini_ai and self._mini_ai.is_loaded:
            return self._multi_attempt_consensus(
                input_data, prompt, start_time
            )

        # Fallback to single-attempt with retry
        return self._single_attempt_with_retry(
            input_data, prompt, start_time
        )

    def _multi_attempt_consensus(self, input_data: VerdictInput,
                                  prompt: str,
                                  start_time: float) -> VerdictOutput:
        """
        Multi-attempt consensus: Pregunta al LLM N veces y la mayoría decide.

        Esto es la principal defensa contra respuestas incorrectas del modelo:
        - Si el modelo da respuestas inconsistentes, la mayoría probablemente
          es correcta (ley de grandes números)
        - Si el modelo falla intermitentemente, algunos intentos pueden funcionar
        - El overhead es mínimo (3 llamadas rápidas de 1 token cada una)
        """
        yes_count = 0
        no_count = 0
        raw_responses = []
        total_attempts = 0
        any_timeout = False
        any_ambiguous = False

        for i in range(VERDICT_CONSENSUS_ATTEMPTS):
            # Small delay between consensus attempts
            if i > 0:
                time.sleep(0.2)

            try:
                if self._executor is None:
                    raise RuntimeError("Executor not initialized — VerdictEngine may have been shut down")
                future = self._executor.submit(
                    self._call_llm_safe, prompt, VERDICT_MAX_TOKENS
                )
                raw_response = future.result(timeout=VERDICT_TIMEOUT_S)
                total_attempts += 1

                if raw_response:
                    raw_responses.append(raw_response)
                    parsed = self._parse_verdict(raw_response)

                    if parsed == Verdict.YES:
                        yes_count += 1
                    elif parsed == Verdict.NO:
                        no_count += 1
                    else:
                        # Ambiguous
                        no_count += 1
                        any_ambiguous = True
                else:
                    no_count += 1
            except concurrent.futures.TimeoutError:
                total_attempts += 1
                no_count += 1
                any_timeout = True
                logger.warning(
                    f"VerdictEngine: Consensus attempt {i + 1} timed out"
                )
            except Exception as e:
                total_attempts += 1
                no_count += 1
                logger.warning(
                    f"VerdictEngine: Consensus attempt {i + 1} failed: {e}"
                )

            # Early exit: Clear majority
            if yes_count >= VERDICT_CONSENSUS_THRESHOLD:
                break
            if no_count >= VERDICT_CONSENSUS_THRESHOLD:
                break

        # Determine verdict by majority
        elapsed = time.time() - start_time
        self._total_time += elapsed
        evidence_summary = self._build_evidence_summary_from_input(input_data)

        if yes_count >= VERDICT_CONSENSUS_THRESHOLD:
            # Majority YES
            self._yes_count += 1
            latency_s = elapsed
            self._record_success(latency_s, any_ambiguous)

            confidence = min(yes_count / max(total_attempts, 1) + 0.1, 1.0)

            self._audit_result(
                input_data.question, "YES", "llm_consensus",
                True, confidence, int(elapsed * 1000), 0,
                len(input_data.evidence_for), len(input_data.evidence_against),
                input_data.consensus_score,
                raw_response="; ".join(raw_responses[:3])
            )

            return VerdictOutput(
                verdict=Verdict.YES,
                confidence=confidence,
                source="llm_consensus",
                evidence_summary=evidence_summary,
                llm_used=True,
                llm_raw_response="; ".join(raw_responses[:3]),
                retry_count=0,
            )
        else:
            # Majority NO or tie → NO (precaution principle)
            self._no_count += 1
            all_failed = yes_count == 0 and no_count == 0
            if all_failed:
                self._fallback_verdicts += 1
                source = "fallback"
            else:
                source = "llm_consensus"

            self._record_failure(
                elapsed, was_timeout=any_timeout, was_ambiguous=any_ambiguous
            )

            self._audit_result(
                input_data.question, "NO", source,
                yes_count > 0, 0.0, int(elapsed * 1000), 0,
                len(input_data.evidence_for), len(input_data.evidence_against),
                input_data.consensus_score,
                was_timeout=any_timeout, was_ambiguous=any_ambiguous,
                raw_response="; ".join(raw_responses[:3])
            )

            confidence = 0.0 if all_failed else min(no_count / max(total_attempts, 1), 1.0)

            return VerdictOutput(
                verdict=Verdict.NO,
                confidence=confidence,
                source=source,
                evidence_summary=evidence_summary + (
                    " [FALLBACK: LLM unavailable]" if all_failed
                    else " [CONSENSUS: Majority NO]"
                ),
                llm_used=yes_count > 0 or no_count > 0,
                llm_raw_response="; ".join(raw_responses[:3]),
                retry_count=0,
            )

    def _single_attempt_with_retry(self, input_data: VerdictInput,
                                    prompt: str,
                                    start_time: float) -> VerdictOutput:
        """
        Single-attempt verdict with retry and exponential backoff.
        Used when multi-attempt consensus is disabled.
        """
        raw_response = None
        retry_count = 0
        any_timeout = False
        any_ambiguous = False

        max_retries = VERDICT_MAX_RETRIES
        if self._resilience:
            max_retries = self._resilience.retry_config.max_attempts

        if self._mini_ai and self._mini_ai.is_loaded:
            for attempt in range(max_retries):
                retry_count = attempt

                # Delay between retries
                if attempt > 0:
                    delay = self._compute_retry_delay(attempt)
                    logger.info(
                        f"VerdictEngine: Retry {attempt}/{max_retries} after {delay:.1f}s"
                    )
                    time.sleep(delay)

                try:
                    if self._executor is None:
                        raise RuntimeError("Executor not initialized — VerdictEngine may have been shut down")
                    future = self._executor.submit(
                        self._call_llm_safe, prompt, VERDICT_MAX_TOKENS
                    )
                    raw_response = future.result(timeout=VERDICT_TIMEOUT_S)
                    if raw_response:
                        parsed = self._parse_verdict(raw_response)
                        if parsed is not None:
                            elapsed = time.time() - start_time
                            self._total_time += elapsed

                            self._record_success(
                                elapsed, was_ambiguous=False
                            )

                            if parsed == Verdict.YES:
                                self._yes_count += 1
                            else:
                                self._no_count += 1

                            evidence_summary = self._build_evidence_summary_from_input(input_data)

                            self._audit_result(
                                input_data.question, parsed.value, "llm",
                                True, abs(input_data.consensus_score) + 0.3,
                                int(elapsed * 1000), retry_count,
                                len(input_data.evidence_for), len(input_data.evidence_against),
                                input_data.consensus_score,
                                raw_response=raw_response
                            )

                            return VerdictOutput(
                                verdict=parsed,
                                confidence=abs(input_data.consensus_score) + 0.3,
                                source="llm",
                                evidence_summary=evidence_summary,
                                llm_used=True,
                                llm_raw_response=raw_response,
                                retry_count=retry_count,
                            )
                        else:
                            any_ambiguous = True
                except concurrent.futures.TimeoutError:
                    any_timeout = True
                    logger.warning(
                        f"VerdictEngine: LLM timed out after {VERDICT_TIMEOUT_S}s "
                        f"(attempt {attempt + 1})"
                    )
                except Exception as e:
                    logger.warning(f"VerdictEngine: LLM call failed: {e}")

        # Fallback: NO (principio de precaución)
        elapsed = time.time() - start_time
        self._total_time += elapsed
        self._fallback_verdicts += 1
        self._no_count += 1

        self._record_failure(
            elapsed, was_timeout=any_timeout, was_ambiguous=any_ambiguous
        )

        evidence_summary = self._build_evidence_summary_from_input(input_data)

        self._audit_result(
            input_data.question, "NO", "fallback",
            raw_response is not None, 0.0, int(elapsed * 1000), retry_count,
            len(input_data.evidence_for), len(input_data.evidence_against),
            input_data.consensus_score,
            was_timeout=any_timeout, was_ambiguous=any_ambiguous,
            raw_response=raw_response or ""
        )

        return VerdictOutput(
            verdict=Verdict.NO,
            confidence=0.0,
            source="fallback",
            evidence_summary=evidence_summary + " [FALLBACK: LLM unavailable or ambiguous]",
            llm_used=raw_response is not None,
            llm_raw_response=raw_response or "",
            retry_count=retry_count,
        )
