"""VerdictMixin attempt methods: single and multi-attempt consensus."""

import time
import logging
import concurrent.futures
from typing import Dict, Any, Optional

from ._constants import (
    VERDICT_MAX_RETRIES,
    VERDICT_TIMEOUT_S,
    VERDICT_CONSENSUS_ATTEMPTS,
    VERDICT_CONSENSUS_THRESHOLD,
    VERDICT_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


class VerdictAttemptsMixin:
    """Single-attempt and multi-attempt consensus verdict logic."""

    def _verdict_single_attempt(self, user_prompt: str, question: str,
                                 start_time: float, evidence_for: str,
                                 evidence_against: str, consensus_hint: float) -> Dict[str, Any]:
        """
        Try to obtain a verdict with retry and exponential backoff.
        """
        raw_response: Optional[str] = None
        retry_count = 0
        last_was_timeout = False
        last_was_ambiguous = False

        max_retries = VERDICT_MAX_RETRIES
        if self._verdict_resilience:
            max_retries = self._verdict_resilience.retry_config.max_attempts

        for attempt in range(max_retries):
            retry_count = attempt

            # Delay between retries (not on first attempt)
            if attempt > 0:
                delay = self._compute_retry_delay(attempt)
                logger.info(f"VerdictMixin: Retry {attempt}/{max_retries} after {delay:.1f}s")
                time.sleep(delay)

            # Try LLM with strict timeout
            try:
                self._ensure_verdict_executor()
                future = self._verdict_executor.submit(
                    self._verdict_llm_call, user_prompt
                )
                raw_response = future.result(timeout=VERDICT_TIMEOUT_S)
                if raw_response:
                    # Parse response
                    parsed = self._parse_verdict_response(raw_response)

                    if parsed is not None:
                        # Valid response!
                        latency_s = time.time() - start_time
                        self._record_verdict_success(
                            latency_s, parsed == "YES"
                        )
                        elapsed_ms = int(latency_s * 1000)

                        if parsed == "YES":
                            self._verdict_yes += 1
                        else:
                            self._verdict_no += 1

                        self._audit_verdict(
                            question, parsed, "llm", True,
                            min(abs(consensus_hint) + 0.3, 1.0),
                            elapsed_ms, retry_count,
                            evidence_for, evidence_against, consensus_hint,
                            raw_response=raw_response
                        )

                        return {
                            "verdict": parsed,
                            "confidence": min(abs(consensus_hint) + 0.3, 1.0),
                            "source": "llm",
                            "raw_response": raw_response,
                            "time_ms": elapsed_ms,
                            "retry_count": retry_count,
                        }
                    else:
                        # Ambiguous response
                        last_was_ambiguous = True
                        logger.warning(
                            f"VerdictMixin: Ambiguous response on attempt {attempt + 1}"
                        )
            except concurrent.futures.TimeoutError:
                last_was_timeout = True
                logger.warning(
                    f"VerdictMixin: Timeout ({VERDICT_TIMEOUT_S}s), attempt {attempt + 1}"
                )
            except Exception as e:
                logger.warning(f"VerdictMixin: LLM error on attempt {attempt + 1}: {e}")

        # All attempts failed
        latency_s = time.time() - start_time
        self._record_verdict_failure(
            latency_s, was_timeout=last_was_timeout, was_ambiguous=last_was_ambiguous
        )

        # Fallback: NO (precautionary principle)
        self._verdict_fallback += 1
        self._verdict_no += 1
        elapsed_ms = int((time.time() - start_time) * 1000)

        self._audit_verdict(
            question, "NO", "fallback", False, 0.0,
            elapsed_ms, retry_count,
            evidence_for, evidence_against, consensus_hint,
            was_timeout=last_was_timeout, was_ambiguous=last_was_ambiguous,
            raw_response=raw_response or ""
        )

        return {
            "verdict": "NO",
            "confidence": 0.0,
            "source": "fallback",
            "raw_response": raw_response or "",
            "time_ms": elapsed_ms,
            "retry_count": retry_count,
        }

    def _verdict_multi_attempt(self, user_prompt: str, question: str,
                                start_time: float, evidence_for: str,
                                evidence_against: str,
                                consensus_hint: float) -> Dict[str, Any]:
        """
        Multi-attempt consensus: Ask the LLM N times and majority decides.

        This significantly reduces the probability of an incorrect verdict
        due to a random model response.

        Example: If asked 3 times and 2+ say YES → verdict = YES
        """
        yes_count = 0
        no_count = 0
        raw_responses: list = []
        total_attempts = 0

        for i in range(VERDICT_CONSENSUS_ATTEMPTS):
            # Small delay between consensus attempts to let model cool down
            if i > 0:
                time.sleep(0.3)

            try:
                self._ensure_verdict_executor()
                future = self._verdict_executor.submit(
                    self._verdict_llm_call, user_prompt
                )
                raw = future.result(timeout=VERDICT_TIMEOUT_S)
                total_attempts += 1

                if raw:
                    raw_responses.append(raw)
                    parsed = self._parse_verdict_response(raw)
                    if parsed == "YES":
                        yes_count += 1
                    elif parsed == "NO":
                        no_count += 1
                    # None (ambiguous) counts as NO implicitly
                else:
                    no_count += 1  # No response = NO
            except concurrent.futures.TimeoutError:
                no_count += 1  # Timeout = NO
                total_attempts += 1
                logger.warning(
                    f"VerdictMixin: Consensus attempt {i + 1} timed out"
                )
            except Exception as e:
                no_count += 1
                total_attempts += 1
                logger.warning(
                    f"VerdictMixin: Consensus attempt {i + 1} failed: {e}"
                )

            # Early exit: If we already have a clear majority
            if yes_count >= VERDICT_CONSENSUS_THRESHOLD:
                break
            if no_count >= VERDICT_CONSENSUS_THRESHOLD:
                break

        # Determine verdict by majority
        latency_s = time.time() - start_time
        elapsed_ms = int(latency_s * 1000)

        if yes_count >= VERDICT_CONSENSUS_THRESHOLD:
            # Majority YES
            self._verdict_yes += 1
            self._record_verdict_success(latency_s, True)
            confidence = min(yes_count / total_attempts + 0.1, 1.0)

            self._audit_verdict(
                question, "YES", "llm_consensus", True,
                confidence, elapsed_ms, 0,
                evidence_for, evidence_against, consensus_hint,
                raw_response="; ".join(raw_responses[:3])
            )

            return {
                "verdict": "YES",
                "confidence": confidence,
                "source": "llm_consensus",
                "raw_response": "; ".join(raw_responses[:3]),
                "time_ms": elapsed_ms,
                "retry_count": 0,
                "consensus_detail": {
                    "yes_count": yes_count,
                    "no_count": no_count,
                    "total_attempts": total_attempts,
                },
            }
        else:
            # Majority NO (or tie → NO by precaution principle)
            self._verdict_no += 1
            was_all_failure = yes_count == 0 and no_count == 0
            if was_all_failure:
                self._verdict_fallback += 1
                source = "fallback"
            else:
                source = "llm_consensus"

            self._record_verdict_failure(
                latency_s, was_timeout=no_count > 0 and yes_count == 0
            )

            self._audit_verdict(
                question, "NO", source, yes_count > 0,
                0.0, elapsed_ms, 0,
                evidence_for, evidence_against, consensus_hint,
                raw_response="; ".join(raw_responses[:3])
            )

            return {
                "verdict": "NO",
                "confidence": 0.0 if was_all_failure else min(no_count / max(total_attempts, 1), 1.0),
                "source": source,
                "raw_response": "; ".join(raw_responses[:3]),
                "time_ms": elapsed_ms,
                "retry_count": 0,
                "consensus_detail": {
                    "yes_count": yes_count,
                    "no_count": no_count,
                    "total_attempts": total_attempts,
                },
            }
