"""
ZENIC-AGENTS — Email Parts (Phase 2)

Sub-modules for the enhanced EmailExecutor infrastructure:
  - templates: Email template engine (invoice, reminder, alert, welcome, low_stock)
  - rate_limiter: Per-recipient and global email rate limiting
  - oauth2: OAuth2 token manager for authorized services (Graph API, ServiceNow, etc.)
  - graph_api: Microsoft Graph API email provider
"""

from __future__ import annotations

from .templates import EmailTemplateEngine, EmailTemplate
from .rate_limiter import EmailRateLimiter
from .oauth2 import OAuth2TokenManager, OAuth2Config, OAuth2Token
from .graph_api import GraphAPIEmailProvider

__all__ = [
    "EmailTemplateEngine",
    "EmailTemplate",
    "EmailRateLimiter",
    "OAuth2TokenManager",
    "OAuth2Config",
    "OAuth2Token",
    "GraphAPIEmailProvider",
]
