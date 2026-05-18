"""
ZENIC-AGENTS — Microsoft Graph API Email Provider (Phase 2)

Sends emails through the Microsoft Graph API (Office 365 / Exchange Online).
Uses the OAuth2TokenManager for authentication and supports:

  - HTML + plain text bodies
  - CC / BCC recipients
  - File attachments (with upload session for large files > 4 MB)
  - Reply-to addresses
  - Importance levels (low / normal / high)
  - Rate limit tracking from Graph API response headers
  - Retry with exponential backoff
  - Dry-run mode when not configured

Environment variables:
  MSGRAPH_CLIENT_ID      — Azure AD application client ID
  MSGRAPH_CLIENT_SECRET  — Azure AD application client secret
  MSGRAPH_TENANT_ID      — Azure AD tenant ID
  MSGRAPH_TOKEN_URL      — Override token endpoint (optional)
  MSGRAPH_SCOPES         — Comma-separated scopes (default: Mail.Send)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from ..oauth2 import OAuth2TokenManager
from ._types import _HAS_AIOHTTP, _RateLimitState
from ._operations import (
    auto_configure,
    is_configured,
    send_email,
)

logger = logging.getLogger("zenic_agents.email_parts.graph_api")


# ──────────────────────────────────────────────────────────────
#  GRAPH API EMAIL PROVIDER
# ──────────────────────────────────────────────────────────────

class GraphAPIEmailProvider:
    """Microsoft Graph API email provider for sending emails.

    Uses OAuth2TokenManager for authentication with automatic
    token refresh. Supports full email features including
    attachments, CC/BCC, reply-to, and importance levels.

    Thread-safe: uses asyncio.Lock for send operations.

    Dry-run mode: When the service is not configured or aiohttp
    is unavailable, send_email() returns success with dry_run=True
    in the response data instead of making network requests.
    """

    def __init__(
        self,
        token_manager: Optional[OAuth2TokenManager] = None,
        service_name: str = "msgraph",
        from_email: str = "",
    ) -> None:
        """Initialize the Graph API email provider.

        Args:
            token_manager: OAuth2TokenManager instance. If None,
                uses the global default and auto-registers from
                MSGRAPH_* environment variables.
            service_name: Service name in the token manager.
            from_email: Default sender email (can be overridden per-send).
        """
        self._service_name = service_name
        self._from_email = from_email
        self._lock = asyncio.Lock()
        self._rate_limit = _RateLimitState()

        # Mutable refs for counters (needed for _operations functions)
        self._send_count_ref = [0]
        self._error_count_ref = [0]
        self._dry_run_count_ref = [0]

        # Set up token manager
        if token_manager is not None:
            self._token_manager = token_manager
        else:
            self._token_manager = self._auto_configure()

    # ── Public API ────────────────────────────────────────────

    async def send_email(
        self,
        to: List[str],
        subject: str,
        body: str = "",
        html: str = "",
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        from_email: str = "",
        attachments: Optional[List[Dict[str, Any]]] = None,
        reply_to: Optional[List[str]] = None,
        importance: str = "normal",
    ) -> Dict[str, Any]:
        """Send an email via Microsoft Graph API.

        Args:
            to: List of recipient email addresses.
            subject: Email subject line.
            body: Plain text body.
            html: HTML body (takes precedence if both body and html provided).
            cc: CC recipients.
            bcc: BCC recipients.
            from_email: Sender email (overrides default).
            attachments: List of attachment dicts with keys:
                - name (str): File name
                - content_bytes (bytes): File content (base64-encoded for <4MB)
                - size (int): File size in bytes
                - content_type (str): MIME type (optional)
            reply_to: Reply-to email addresses.
            importance: Email importance ("low", "normal", "high").

        Returns:
            Dict with keys:
                - success (bool): Whether the send succeeded.
                - message_id (str): Graph API message ID (or dry-run ID).
                - dry_run (bool): True if not actually sent.
                - status_code (int): HTTP status code.
                - error (str): Error message if failed.
                - rate_limit (dict): Current rate limit state.
        """
        return await send_email(
            provider=self,
            to=to,
            subject=subject,
            body=body,
            html=html,
            cc=cc,
            bcc=bcc,
            from_email=from_email,
            attachments=attachments,
            reply_to=reply_to,
            importance=importance,
        )

    @property
    def is_configured(self) -> bool:
        """Check if the provider is configured for actual sending."""
        return self._is_configured()

    @property
    def rate_limit(self) -> Dict[str, Any]:
        """Get current rate limit state."""
        return self._rate_limit.to_dict()

    @property
    def stats(self) -> Dict[str, Any]:
        """Get provider statistics."""
        return {
            "service_name": self._service_name,
            "configured": self._is_configured(),
            "from_email": self._from_email,
            "send_count": self._send_count_ref[0],
            "error_count": self._error_count_ref[0],
            "dry_run_count": self._dry_run_count_ref[0],
            "aiohttp_available": _HAS_AIOHTTP,
            "rate_limit": self._rate_limit.to_dict(),
        }

    # ── Private: Configuration ────────────────────────────────

    def _auto_configure(self) -> OAuth2TokenManager:
        """Auto-configure token manager from environment variables."""
        from_email_ref = [self._from_email]
        manager = auto_configure(self._service_name, from_email_ref)
        self._from_email = from_email_ref[0]
        return manager

    def _is_configured(self) -> bool:
        """Check if we have the minimum configuration to send emails."""
        return is_configured(self._token_manager, self._service_name)


__all__ = ["GraphAPIEmailProvider"]
