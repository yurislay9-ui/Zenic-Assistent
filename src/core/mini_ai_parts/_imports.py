"""
Shared imports, constants, and dataclasses for mini_ai_parts.
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# === Model Configuration ===
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "models")
MODEL_FILENAME = "qwen3-0.6b-q4_k_m.gguf"
MODEL_PATH = os.path.join(MODEL_DIR, MODEL_FILENAME)

# Bounded task limits (prevent runaway generation)
MAX_TOKENS_CLASSIFY = 200       # Allow thinking + answer
MAX_TOKENS_EXTRACT = 200
MAX_TOKENS_PATTERN = 250
MAX_TOKENS_TEMPLATE = 300
MAX_TOKENS_GENERATE = 400
MAX_TOKENS_CODE_GENERATE = 1500   # Separate limit for full code generation (was capped at 600 via MAX_TOKENS_AGENT)
MAX_TOKENS_EXPLAIN = 200
MAX_TOKENS_SUBTASK = 200

LLM_TIMEOUT_S = float(os.environ.get("ZENIC_LLM_TIMEOUT_S", "120.0"))  # ARM needs 120s (was 60s, still not enough for Qwen3 on ARM)
N_CTX = 2048                    # Context window
N_THREADS = int(os.environ.get("ZENIC_LLM_THREADS", "4"))  # CPU threads (configurable for ARM/low-power)
# Phase 5: Deterministic temperature — T=0.0 is the ONLY way to guarantee
# identical LLM outputs for the same input. T=0.1 allows probabilistic
# sampling which breaks determinism. When ZENIC_DETERMINISTIC=1 (default),
# force temperature to 0.0 (greedy decoding).
_DETERMINISTIC_MODE = os.environ.get("ZENIC_DETERMINISTIC", "1") == "1"
TEMPERATURE = 0.0 if _DETERMINISTIC_MODE else float(os.environ.get("ZENIC_LLM_TEMPERATURE", "0.1"))


@dataclass
class IntentResult:
    """Resultado de classify_intent con confidence."""
    operation: str = "SEARCH"        # CREATE|REFACTOR|DELETE|SEARCH|ANALYZE|EXPLAIN|DEBUG|OPTIMIZE
    goal: str = "FEATURE_ADD"        # COMPLEXITY_REDUCTION|MODERN_PATTERN|BUG_FIX|FEATURE_ADD|SECURITY_HARDEN|PERFORMANCE|READABILITY
    confidence: float = 0.0          # 0.0-1.0
    source: str = "fallback"         # "llm" or "fallback"
