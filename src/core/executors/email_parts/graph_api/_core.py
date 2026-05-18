"""graph_api — Core implementation (class definition + public API)."""

from __future__ import annotations

import base64
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from ._types import *  # noqa: F403
from ._helpers import _send_with_retry, _send_once, _dry_run_response, _upload_attachment_session
from ._transport import GraphAPITransportMixin


class GraphAPIEmailProvider(GraphAPITransportMixin):
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
        token_manager: Optional[OAuth2TokenManager] = None,  # noqa: F821
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
        self._lock = asyncio.Lock()  # noqa: F821
        self._rate_limit = _RateLimitState()  # noqa: F821
        self._send_count: int = 0
        self._error_count: int = 0
        self._dry_run_count: int = 0

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
        """Send an email via Microsoft Graph API."""
        start = time.monotonic()

        # Validate importance
        valid_importance = {"low", "normal", "high"}
        if importance not in valid_importance:
            importance = "normal"

        # Determine sender
        sender = from_email or self._from_email

        # Build the Graph API request payload
        payload = self._build_payload(
            to=to, subject=subject, body=body, html=html,
            cc=cc or [], bcc=bcc or [], sender=sender,
            reply_to=reply_to or [], importance=importance,
            attachments=attachments or [],
        )

        # Check for dry-run conditions
        if not self._is_configured():
            return self._dry_run_response(
                to=to, subject=subject, payload=payload,
                reason="service_not_configured",
            )

        if not _HAS_AIOHTTP:  # noqa: F821
            return self._dry_run_response(
                to=to, subject=subject, payload=payload,
                reason="aiohttp_not_available",
            )

        # Send with retry
        result = await self._send_with_retry(payload, sender)

        elapsed = round((time.monotonic() - start) * 1000, 2)
        result["duration_ms"] = elapsed
        result["recipients"] = to
        result["subject"] = subject

        return result

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
            "send_count": self._send_count,
            "error_count": self._error_count,
            "dry_run_count": self._dry_run_count,
            "aiohttp_available": _HAS_AIOHTTP,  # noqa: F821
            "rate_limit": self._rate_limit.to_dict(),
        }

    # ── Private: Configuration ────────────────────────────────

    def _auto_configure(self) -> "OAuth2TokenManager":  # noqa: F821
        """Auto-configure token manager from environment variables."""
        from .oauth2 import get_default_token_manager
        manager = get_default_token_manager()

        token_status = manager.get_token_status(self._service_name)
        if not token_status.get("registered"):
            config = config_from_env("MSGRAPH")  # noqa: F821
            if config.is_configured:
                if not config.scopes:
                    config.scopes = _DEFAULT_SCOPES  # noqa: F821
                manager.register_service(self._service_name, config)

        if not self._from_email:
            self._from_email = os.environ.get("MSGRAPH_FROM_EMAIL", "")

        return manager

    def _is_configured(self) -> bool:
        """Check if we have the minimum configuration to send emails."""
        token_status = self._token_manager.get_token_status(self._service_name)
        return token_status.get("configured", False)

    # ── Private: Payload Construction ─────────────────────────

    @staticmethod
    def _build_payload(
        to: List[str],
        subject: str,
        body: str,
        html: str,
        cc: List[str],
        bcc: List[str],
        sender: str,
        reply_to: List[str],
        importance: str,
        attachments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build the Graph API sendMail request payload."""
        if html:
            content_type = "HTML"
            content = html
        else:
            content_type = "Text"
            content = body or " "

        to_recipients = [
            {"emailAddress": {"address": addr}} for addr in to if addr
        ]

        message: Dict[str, Any] = {
            "subject": subject,
            "body": {"contentType": content_type, "content": content},
            "toRecipients": to_recipients,
            "importance": importance,
        }

        if cc:
            message["ccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in cc if addr
            ]
        if bcc:
            message["bccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in bcc if addr
            ]
        if reply_to:
            message["replyTo"] = [
                {"emailAddress": {"address": addr}} for addr in reply_to if addr
            ]
        if sender:
            message["from"] = {"emailAddress": {"address": sender}}

        # Attachments (inline for small files)
        if attachments:
            inline_attachments = []
            for att in attachments:
                att_size = att.get("size", 0)
                if att_size <= _MAX_ATTACHMENT_SIZE_INLINE:  # noqa: F821
                    import base64 as b64
                    content_bytes = att.get("content_bytes", b"")
                    if isinstance(content_bytes, bytes):
                        b64_content = b64.b64encode(content_bytes).decode("ascii")
                    else:
                        b64_content = str(content_bytes)

                    inline_attachments.append({
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": att.get("name", "attachment"),
                        "contentType": att.get("content_type", "application/octet-stream"),
                        "contentBytes": b64_content,
                    })
            if inline_attachments:
                message["attachments"] = inline_attachments

        payload: Dict[str, Any] = {"message": message}
        if sender:
            payload["saveToSentItems"] = True

        return payload


__all__ = ["GraphAPIEmailProvider"]
