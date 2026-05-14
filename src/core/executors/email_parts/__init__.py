"""
ZENIC-AGENTS - Email Parts (Phase 3)

Sub-modules for the enhanced EmailExecutor:
  - templates: Email template engine (invoice, reminder, alert, custom)
  - rate_limiter: Per-recipient and global email rate limiting
"""

from .templates import EmailTemplateEngine, EmailTemplate
from .rate_limiter import EmailRateLimiter

__all__ = [
    "EmailTemplateEngine",
    "EmailTemplate",
    "EmailRateLimiter",
]
