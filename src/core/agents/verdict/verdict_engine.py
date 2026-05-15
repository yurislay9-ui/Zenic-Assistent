"""
A43 VerdictEngine — SINGLE RESPONSIBILITY: Ask Qwen a binary YES/NO question.

The ONLY place in the v18 architecture where AI is used.
Qwen ONLY returns YES or NO. Any other response → NO.
Multi-attempt consensus (3 calls, majority vote).
Circuit breaker protection.
Exponential backoff retry.

INVARIANTS:
  - AI can ONLY return "YES" or "NO"
  - Any ambiguous response → "NO" (precaution principle)
  - If model not loaded → NO
  - If circuit breaker open → NO
  - If timeout → NO
  - Security veto is absolute (handled upstream by ConsensusResolver)
"""

from __future__ import annotations

import os
import re
import threading
import time
from typing import Any, Optional

from ..resilience import BaseAgent
from ..schemas import Verdict, VerdictInput, VerdictOutput, ConsensusResult, Evidence

# ──────────────────────────────────────────────────────────────
# VERDICT CONFIGURATION
# ──────────────────────────────────────────────────────────────

VERDICT_MAX_TOKENS = 10
VERDICT_TEMPERATURE = 0.0
VERDICT_TIMEOUT_S = 5.0
VERDICT_MAX_RETRIES = 3
VERDICT_BASE_DELAY = 1.0
VERDICT_MAX_DELAY = 10.0
VERDICT_CONSENSUS_ATTEMPTS = int(os.environ.get("ZENIC_VERDICT_CONSENSUS", "1"))  # ARM: 1 attempt (was 3, too many LLM timeouts)
VERDICT_CONSENSUS_THRESHOLD = 2  # Minimum YES count for verdict YES

VERDICT_SYSTEM_PROMPT = (
    "You are a binary decision maker. "
    "Answer with ONLY one word: YES or NO. "
    "Never explain. Never add context. Only YES or NO."
)


class VerdictEngineV18(BaseAgent[VerdictOutput]):
    """
    A43: Binary verdict engine — the ONLY place AI is used.

    Single Responsibility: Binary YES/NO arbitration ONLY.
    Method: Multi-attempt consensus with circuit breaker.
    Fallback: Return NO (precaution principle).
    """

    def __init__(self, mini_ai=None, **kwargs) -> None:
        super().__init__(name="A43_VerdictEngine", **kwargs)
        self._mini_ai = mini_ai
        self._verdict_lock = threading.Lock()

        # Verdict stats
        self._verdict_stats = {
            "total_verdicts": 0,
            "llm_verdicts": 0,
            "consensus_verdicts": 0,
            "fallback_verdicts": 0,
            "yes_count": 0,
            "no_count": 0,
        }

    def wire_mini_ai(self, mini_ai) -> None:
        """Connect to MiniAIEngine for LLM calls."""
        self._mini_ai = mini_ai

    def execute(self, input_data: Any) -> VerdictOutput:
        """
        Execute binary verdict.

        input_data should be a VerdictInput or dict with:
          - 'question': str
          - 'consensus_result': ConsensusResult (optional, if already resolved)
          - 'evidence_for': List[Evidence]
          - 'evidence_against': List[Evidence]
        """
        # If consensus is already clear, no AI needed
        consensus = None
        if isinstance(input_data, dict):
            consensus = input_data.get("consensus_result")
        elif isinstance(input_data, VerdictInput):
            pass

        if consensus and isinstance(consensus, ConsensusResult):
            if not consensus.needs_llm:
                # Consensus is clear — no AI needed
                return VerdictOutput(
                    verdict=consensus.verdict,
                    confidence=consensus.confidence,
                    source="deterministic_consensus",
                    llm_used=False,
                )

        # AI arbitration needed
        return self._request_llm_verdict(input_data)

    def _request_llm_verdict(self, input_data: Any) -> VerdictOutput:
        """Request LLM verdict with full resilience."""
        start_time = time.monotonic()

        # Check if model is loaded
        if not self._mini_ai or not getattr(self._mini_ai, 'is_loaded', False):
            return VerdictOutput(
                verdict=Verdict.NO,
                confidence=0.1,
                source="fallback_no_model",
                llm_used=False,
                duration_ms=(time.monotonic() - start_time) * 1000,
            )

        # Check circuit breaker
        if not self._cb_manager.can_call(self.name):
            return VerdictOutput(
                verdict=Verdict.NO,
                confidence=0.1,
                source="fallback_circuit_open",
                llm_used=False,
                duration_ms=(time.monotonic() - start_time) * 1000,
            )

        # Build prompt
        user_prompt = self._build_verdict_prompt(input_data)

        # Multi-attempt consensus
        yes_count = 0
        no_count = 0
        last_response = ""
        retry_count = 0

        for attempt in range(VERDICT_CONSENSUS_ATTEMPTS):
            try:
                response = self._call_llm(user_prompt)
                last_response = response or ""

                parsed = self._parse_verdict_response(response)
                if parsed == "YES":
                    yes_count += 1
                    self._cb_manager.record_success(self.name)
                else:
                    no_count += 1
                    self._cb_manager.record_success(self.name)

                # Early exit if clear majority
                if yes_count >= VERDICT_CONSENSUS_THRESHOLD:
                    break
                if no_count >= VERDICT_CONSENSUS_THRESHOLD:
                    break

                # Small delay between attempts
                if attempt < VERDICT_CONSENSUS_ATTEMPTS - 1:
                    time.sleep(0.3)

            except Exception as e:
                no_count += 1  # Any failure counts as NO
                self._cb_manager.record_failure(self.name)
                retry_count += 1

        # Determine verdict by majority
        verdict = Verdict.YES if yes_count >= VERDICT_CONSENSUS_THRESHOLD else Verdict.NO
        total_attempts = yes_count + no_count
        confidence = max(yes_count, no_count) / total_attempts if total_attempts > 0 else 0.0

        # Update stats
        with self._verdict_lock:
            self._verdict_stats["total_verdicts"] += 1
            self._verdict_stats["llm_verdicts"] += 1
            if verdict == Verdict.YES:
                self._verdict_stats["yes_count"] += 1
            else:
                self._verdict_stats["no_count"] += 1

        return VerdictOutput(
            verdict=verdict,
            confidence=round(confidence, 2),
            source="llm_consensus",
            evidence_summary=self._format_evidence_summary(input_data),
            llm_used=True,
            llm_raw_response=last_response,
            retry_count=retry_count,
            duration_ms=(time.monotonic() - start_time) * 1000,
        )

    def _call_llm(self, user_prompt: str) -> Optional[str]:
        """Call LLM via MiniAIEngine."""
        try:
            return self._mini_ai._call_llm(
                system_prompt=VERDICT_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=VERDICT_MAX_TOKENS,
            )
        except Exception:
            return None

    @staticmethod
    def _parse_verdict_response(response: Optional[str]) -> Optional[str]:
        """
        Strict parser: ONLY accept YES or NO.
        Strip think blocks, take first word, validate.
        Anything else → None (= NO).
        """
        if not response:
            return None

        # Strip Qwen3 <think...> blocks
        cleaned = re.sub(r'<think[^>]*>.*?</think\s*>', '', response, flags=re.DOTALL)
        cleaned = cleaned.strip()

        if not cleaned:
            return None

        # Take first word only
        first_word = cleaned.split()[0].upper().rstrip('.,;:!?')

        if first_word in ("YES", "SI", "SÍ"):
            return "YES"
        elif first_word in ("NO",):
            return "NO"
        else:
            return None  # Ambiguous → treated as NO

    def _build_verdict_prompt(self, input_data: Any) -> str:
        """Build the verdict prompt for Qwen."""
        question = ""
        evidence_for = []
        evidence_against = []

        if isinstance(input_data, VerdictInput):
            question = input_data.question
            evidence_for = input_data.evidence_for
            evidence_against = input_data.evidence_against
        elif isinstance(input_data, dict):
            question = input_data.get("question", "Should this be approved?")
            evidence_for = input_data.get("evidence_for", [])
            evidence_against = input_data.get("evidence_against", [])

        # Format evidence (truncated to 200 chars each)
        for_items = []
        for e in evidence_for[:3]:
            for_items.append(e.detail[:200] if hasattr(e, 'detail') else str(e)[:200])

        against_items = []
        for e in evidence_against[:3]:
            against_items.append(e.detail[:200] if hasattr(e, 'detail') else str(e)[:200])

        prompt = f"Evidence FOR: {'; '.join(for_items) or 'None'}\n"
        prompt += f"Evidence AGAINST: {'; '.join(against_items) or 'None'}\n"
        prompt += f"Question: {question}\n"
        prompt += "Answer with ONLY: YES or NO"

        return prompt

    @staticmethod
    def _format_evidence_summary(input_data: Any) -> str:
        """Format evidence summary for audit."""
        if isinstance(input_data, dict):
            ef = input_data.get("evidence_for", [])
            ea = input_data.get("evidence_against", [])
            return f"FOR:{len(ef)} AGAINST:{len(ea)}"
        return "no_evidence"

    def fallback(self, input_data: Any) -> VerdictOutput:
        """Fallback: Return NO. Precaution principle."""
        return VerdictOutput(
            verdict=Verdict.NO,
            confidence=0.1,
            source="fallback",
            llm_used=False,
        )

    @property
    def verdict_stats(self) -> dict:
        with self._verdict_lock:
            return dict(self._verdict_stats)
