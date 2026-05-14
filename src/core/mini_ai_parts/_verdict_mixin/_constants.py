"""Constants and configuration for VerdictMixin."""

import os

# === Strict verdict configuration ===
VERDICT_MAX_TOKENS = 10          # Only needs 1 token
VERDICT_TEMPERATURE = 0.0        # Absolute determinism
VERDICT_TIMEOUT_S = 15.0         # Timeout per attempt (was 5s, too short for ARM)
VERDICT_MAX_RETRIES = 3          # Retries with exponential backoff
VERDICT_BASE_DELAY = 1.0         # Base delay between retries (seconds)
VERDICT_MAX_DELAY = 10.0         # Maximum delay between retries
VERDICT_CONSENSUS_ATTEMPTS = int(os.environ.get("ZENIC_VERDICT_CONSENSUS", "1"))  # ARM: 1 attempt
VERDICT_CONSENSUS_THRESHOLD = 2  # Minimum YES for verdict YES

VERDICT_SYSTEM_PROMPT = (
    "You are a binary decision maker. "
    "Reply with ONLY one word: YES or NO. "
    "Never explain. Never add anything else."
)

# Import resilience patterns
try:
    from ..verdict_parts.resilience import (
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
