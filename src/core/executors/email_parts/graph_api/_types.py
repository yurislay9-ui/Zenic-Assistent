"""
ZENIC-AGENTS — Microsoft Graph API Email Provider Types (Phase 2)

Constants, rate limit tracking, and optional dependency checks.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict

# ──────────────────────────────────────────────────────────────
#  OPTIONAL DEPENDENCY CHECK
# ──────────────────────────────────────────────────────────────

try:
    import aiohttp
    _HAS_AIOHTTP = True
except ImportError:
    _HAS_AIOHTTP = False


# ──────────────────────────────────────────────────────────────
#  CONSTANTS
# ──────────────────────────────────────────────────────────────

_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
_MAX_ATTACHMENT_SIZE_INLINE = 4 * 1024 * 1024   # 4 MB — inline in send request
_MAX_ATTACHMENT_SIZE_UPLOAD = 150 * 1024 * 1024  # 150 MB — via upload session
_MAX_RETRIES = 3
_INITIAL_BACKOFF_SECONDS = 1.0
_BACKOFF_MULTIPLIER = 2.0

_DEFAULT_SCOPES = ["https://graph.microsoft.com/Mail.Send"]


# ──────────────────────────────────────────────────────────────
#  RATE LIMIT TRACKING
# ──────────────────────────────────────────────────────────────

@dataclass
class _RateLimitState:
    """Tracks Graph API rate limit info from response headers."""
    remaining: int = -1
    reset_at: float = 0.0
    limit: int = -1
    last_updated: float = 0.0

    def update_from_headers(self, headers: Dict[str, str]) -> None:
        """Update rate limit state from Graph API response headers."""
        # Graph API uses these headers (when available)
        remaining = headers.get("RateLimit-Remaining", headers.get("x-rate-remaining", ""))
        limit = headers.get("RateLimit-Limit", headers.get("x-rate-limit", ""))
        reset = headers.get("RateLimit-Reset", headers.get("x-rate-reset", ""))

        if remaining:
            try:
                self.remaining = int(remaining)
            except (ValueError, TypeError):
                pass
        if limit:
            try:
                self.limit = int(limit)
            except (ValueError, TypeError):
                pass
        if reset:
            try:
                self.reset_at = time.time() + float(reset)
            except (ValueError, TypeError):
                pass

        self.last_updated = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "remaining": self.remaining,
            "limit": self.limit,
            "reset_at": self.reset_at,
            "last_updated": self.last_updated,
        }
