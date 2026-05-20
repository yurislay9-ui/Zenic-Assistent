"""email_executor — Type definitions."""

from __future__ import annotations

import asyncio
import email.encoders
import email.mime.multipart
import email.mime.text
import email.mime.base
import email.utils
import logging
import os
import smtplib
import ssl
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence

from .base import ActionExecutor, ActionResult, _validate_email, _HAS_AIOSMTPLIB, _HAS_AIOHTTP
from .email_parts import EmailTemplateEngine, EmailRateLimiter
from .email_parts.graph_api import GraphAPIEmailProvider
from .email_parts.oauth2 import OAuth2TokenManager, OAuth2Config
from .email_parts.rate_limiter import RateLimitConfig, RateLimitResult

logger = logging.getLogger(__name__)

# ── Optional: aiosmtplib ──────────────────────────────────────────

try:
    import aiosmtplib  # type: ignore[import-unresolved]
    _HAS_AIOSMTPLIB_LOCAL = True
except ImportError:
    _HAS_AIOSMTPLIB_LOCAL = False

# ── Optional: urllib fallback ─────────────────────────────────────

try:
    import urllib.request
    import urllib.error
    _HAS_URLLIB = True
except ImportError:
    _HAS_URLLIB = False

# ── Constants ──────────────────────────────────────────────────────

_VALID_MODES = frozenset({"smtp", "graph_api", "auto"})
_VALID_IMPORTANCE = frozenset({"low", "normal", "high"})
_SMTP_TIMEOUT = 30  # seconds

