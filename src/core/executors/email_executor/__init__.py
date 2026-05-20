"""
ZENIC-AGENTS — Email ActionExecutor (Phase 2)

Enhanced email executor supporting both SMTP and Microsoft Graph API.

Modes:
  - "smtp"       → Sends via SMTP (aiosmtplib preferred, smtplib fallback)
  - "graph_api"  → Sends via Microsoft Graph API (OAuth2 + aiohttp)
  - "auto"       → Tries Graph API first, falls back to SMTP

Features:
  - Template rendering via EmailTemplateEngine
  - Per-recipient and global rate limiting via EmailRateLimiter
  - CC / BCC / reply-to / importance / attachments
  - Environment variable fallbacks for all SMTP and Graph API config
  - Dry-run mode when nothing is configured
  - Thread-safe statistics

Design invariants:
  1. Never raises from execute() — always returns ActionResult.
  2. Uses aiosmtplib when available; falls back to smtplib.
  3. Uses aiohttp for Graph API when available.
  4. Dry-run when neither SMTP nor Graph API is configured.
  5. Thread-safe counters via threading.Lock.
"""

from ._executor import EmailExecutor
from ._composer import (
    build_mime_message,
    resolve_recipients,
    build_dry_run_result,
)

__all__ = [
    "EmailExecutor",
    "build_mime_message",
    "resolve_recipients",
    "build_dry_run_result",
]
