"""whatsapp — Type definitions."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import threading
import time
from typing import Any, Dict, FrozenSet, List, Optional
from urllib.parse import urlparse

from .._formatter import (
    MessageFormatter,
    build_whatsapp_interactive_buttons,
    format_whatsapp_text,
    truncate,
)
from .._protocol import ChannelProvider, InboundChannelProvider
from .._types import (
    ChannelCapability,
    ChannelMessage,
    ChannelResponse,
    ConfirmationHandler,
    ConfirmationRequest,
    ConfirmationResult,
    DeliveryStatus,
    MessageHandler,
    RateLimitInfo,
)

logger = logging.getLogger("zenic_agents.channels.whatsapp")


def _validate_url(url: str, allowed_schemes: tuple = ("http", "https")) -> str:
    """Validate URL to prevent SSRF attacks."""
    parsed = urlparse(url)
    if parsed.scheme not in allowed_schemes:
        raise ValueError(f"URL scheme '{parsed.scheme}' not allowed. Use: {allowed_schemes}")
    if not parsed.hostname:
        raise ValueError("URL must have a hostname")
    try:
        ip = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        pass  # hostname is not an IP, that's OK
    else:
        if ip.is_private or ip.is_loopback or ip.is_reserved:
            raise ValueError(f"Access to internal IPs is not allowed: {parsed.hostname}")
    return url


# ── Optional Dependencies ─────────────────────────────────────

try:
    import aiohttp
    _HAS_AIOHTTP = True
except ImportError:
    _HAS_AIOHTTP = False

try:
    import urllib.request
    import urllib.error
    _HAS_URLLIB = True
except ImportError:
    _HAS_URLLIB = False


# ── Constants ─────────────────────────────────────────────────

_WHATSAPP_API_BASE = "https://graph.facebook.com/v18.0"
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.5
_HTTP_TIMEOUT = 30
_MAX_BUTTONS = 3  # WhatsApp limit for interactive buttons

