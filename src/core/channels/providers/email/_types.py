"""email — Type definitions."""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, FrozenSet, List, Optional

from .._formatter import MessageFormatter, truncate, sanitize_html
from .._protocol import ChannelProvider
from .._types import (
    ChannelCapability,
    ChannelMessage,
    ChannelResponse,
    ConfirmationRequest,
    DeliveryStatus,
    RateLimitInfo,
)

logger = logging.getLogger("zenic_agents.channels.email")

# ── Optional Dependencies ─────────────────────────────────────────

try:
    import aiohttp
    _HAS_AIOHTTP = True
except ImportError:
    _HAS_AIOHTTP = False

# ── Constants ──────────────────────────────────────────────────────

_VALID_MODES = frozenset({"smtp", "graph_api", "auto"})

# Priority → importance mapping (ChannelPriority → email importance)
_PRIORITY_TO_IMPORTANCE: Dict[str, str] = {
    "low": "low",
    "normal": "normal",
    "high": "high",
    "urgent": "high",
    "emergency": "high",
}

