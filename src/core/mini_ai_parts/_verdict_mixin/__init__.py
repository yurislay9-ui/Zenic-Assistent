"""
VerdictMixin - Binary verdict capability for MiniAIEngine.

The AI can ONLY answer YES or NO. Nothing else.
If the AI gives an ambiguous response, it counts as NO.
If the AI doesn't respond (timeout), it counts as NO.

v17.1 RESILIENCE IMPROVEMENTS:
  - Circuit Breaker: Protects against downed LLM
  - Retry with exponential backoff: Intelligent retry
  - Health Monitor: LLM health tracking
  - Multi-attempt consensus: Ask N times, majority wins
  - Auditing: Log all decisions
  - Timeout cascade: If the LLM is slow, it adapts
"""

from ._core_mixin import VerdictCoreMixin
from ._attempts_mixin import VerdictAttemptsMixin
from ._helpers_mixin import VerdictHelpersMixin

__all__ = ["VerdictMixin"]


class VerdictMixin(VerdictCoreMixin, VerdictAttemptsMixin, VerdictHelpersMixin):
    """Mixin that adds binary verdict capability to MiniAIEngine.

    The verdict is the ONLY way the AI participates in decisions.
    The AI never generates, never classifies, never explains.
    It only says YES or NO.

    v17.1: Now with resilience patterns:
      - Circuit Breaker: If the LLM fails 3 times, it opens and no more calls
      - Retry with backoff: Intelligent retry with increasing delays
      - Multi-attempt consensus: Ask 3 times, majority decides
      - Health monitoring: LLM health tracking
      - Auditing: Log of all decisions
    """
