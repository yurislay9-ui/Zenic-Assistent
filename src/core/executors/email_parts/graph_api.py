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
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .oauth2 import OAuth2TokenManager, OAuth2Config, config_from_env

logger = logging.getLogger("zenic_agents.email_parts.graph_api")

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
        start = time.monotonic()

        # Validate importance
        valid_importance = {"low", "normal", "high"}
        if importance not in valid_importance:
            importance = "normal"

        # Determine sender
        sender = from_email or self._from_email

        # Build the Graph API request payload
        payload = self._build_payload(
            to=to,
            subject=subject,
            body=body,
            html=html,
            cc=cc or [],
            bcc=bcc or [],
            sender=sender,
            reply_to=reply_to or [],
            importance=importance,
            attachments=attachments or [],
        )

        # Check for dry-run conditions
        if not self._is_configured():
            return self._dry_run_response(
                to=to, subject=subject, payload=payload,
                reason="service_not_configured",
            )

        if not _HAS_AIOHTTP:
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
            "aiohttp_available": _HAS_AIOHTTP,
            "rate_limit": self._rate_limit.to_dict(),
        }

    # ── Private: Configuration ────────────────────────────────

    def _auto_configure(self) -> OAuth2TokenManager:
        """Auto-configure token manager from environment variables."""
        from .oauth2 import get_default_token_manager
        manager = get_default_token_manager()

        # Check if msgraph is already registered (get_default_token_manager auto-registers)
        token_status = manager.get_token_status(self._service_name)
        if not token_status.get("registered"):
            # Try to register from env
            config = config_from_env("MSGRAPH")
            if config.is_configured:
                if not config.scopes:
                    config.scopes = _DEFAULT_SCOPES
                manager.register_service(self._service_name, config)

        # Read default from_email from env
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
        # Body content type
        if html:
            content_type = "HTML"
            content = html
        else:
            content_type = "Text"
            content = body or " "

        # Recipients
        to_recipients = [
            {"emailAddress": {"address": addr}} for addr in to if addr
        ]

        message: Dict[str, Any] = {
            "subject": subject,
            "body": {
                "contentType": content_type,
                "content": content,
            },
            "toRecipients": to_recipients,
            "importance": importance,
        }

        # CC
        if cc:
            message["ccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in cc if addr
            ]

        # BCC
        if bcc:
            message["bccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in bcc if addr
            ]

        # Reply-to
        if reply_to:
            message["replyTo"] = [
                {"emailAddress": {"address": addr}} for addr in reply_to if addr
            ]

        # From
        if sender:
            message["from"] = {"emailAddress": {"address": sender}}

        # Attachments (inline for small files)
        if attachments:
            inline_attachments = []
            for att in attachments:
                att_size = att.get("size", 0)
                if att_size <= _MAX_ATTACHMENT_SIZE_INLINE:
                    import base64
                    content_bytes = att.get("content_bytes", b"")
                    if isinstance(content_bytes, bytes):
                        b64_content = base64.b64encode(content_bytes).decode("ascii")
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

        # Wrap in sendMail envelope
        payload: Dict[str, Any] = {"message": message}
        if sender:
            payload["saveToSentItems"] = True

        return payload

    # ── Private: Sending ──────────────────────────────────────

    async def _send_with_retry(
        self,
        payload: Dict[str, Any],
        sender: str,
    ) -> Dict[str, Any]:
        """Send email with exponential backoff retry."""
        last_error = ""
        for attempt in range(_MAX_RETRIES):
            try:
                result = await self._send_once(payload, sender)
                if result.get("success"):
                    self._send_count += 1
                    return result

                # Check if retryable
                status_code = result.get("status_code", 0)
                if status_code == 429:
                    # Rate limited — respect Retry-After header
                    retry_after = result.get("retry_after_seconds", 60)
                    logger.warning(
                        "GraphAPIEmailProvider: Rate limited (429), retrying after %.1fs",
                        retry_after,
                    )
                    await asyncio.sleep(retry_after)
                    continue

                if status_code in (401, 403):
                    # Auth error — don't retry
                    self._error_count += 1
                    return result

                if status_code >= 500:
                    # Server error — retry with backoff
                    backoff = _INITIAL_BACKOFF_SECONDS * (_BACKOFF_MULTIPLIER ** attempt)
                    logger.warning(
                        "GraphAPIEmailProvider: Server error (%d), retrying in %.1fs "
                        "(attempt %d/%d)",
                        status_code, backoff, attempt + 1, _MAX_RETRIES,
                    )
                    await asyncio.sleep(backoff)
                    last_error = result.get("error", f"HTTP {status_code}")
                    continue

                # Non-retryable error
                self._error_count += 1
                return result

            except asyncio.TimeoutError:
                backoff = _INITIAL_BACKOFF_SECONDS * (_BACKOFF_MULTIPLIER ** attempt)
                logger.warning(
                    "GraphAPIEmailProvider: Request timed out, retrying in %.1fs "
                    "(attempt %d/%d)",
                    backoff, attempt + 1, _MAX_RETRIES,
                )
                last_error = "Request timed out"
                await asyncio.sleep(backoff)

            except Exception as exc:
                backoff = _INITIAL_BACKOFF_SECONDS * (_BACKOFF_MULTIPLIER ** attempt)
                logger.warning(
                    "GraphAPIEmailProvider: Unexpected error: %s, retrying in %.1fs "
                    "(attempt %d/%d)",
                    exc, backoff, attempt + 1, _MAX_RETRIES,
                )
                last_error = str(exc)
                await asyncio.sleep(backoff)

        # All retries exhausted
        self._error_count += 1
        return {
            "success": False,
            "message_id": "",
            "status_code": 0,
            "error": f"All {_MAX_RETRIES} retries exhausted: {last_error}",
        }

    async def _send_once(
        self,
        payload: Dict[str, Any],
        sender: str,
    ) -> Dict[str, Any]:
        """Make a single send attempt via Graph API."""
        async with self._lock:
            token = await self._token_manager.get_token(self._service_name)

        if not token.access_token or token.is_expired:
            return {
                "success": False,
                "message_id": "",
                "status_code": 401,
                "error": "No valid access token available",
            }

        # Determine endpoint
        # If sender specified, use /users/{sender}/sendMail
        # Otherwise, use /me/sendMail
        if sender:
            endpoint = f"{_GRAPH_BASE_URL}/users/{sender}/sendMail"
        else:
            endpoint = f"{_GRAPH_BASE_URL}/me/sendMail"

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": token.authorization_header,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }

                async with session.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response:
                    # Update rate limit from headers
                    resp_headers = {
                        k: v for k, v in response.headers.items()
                    }
                    self._rate_limit.update_from_headers(resp_headers)

                    if response.status == 202:
                        # Success — Graph API returns 202 Accepted
                        message_id = response.headers.get(
                            "Location", f"msg-{uuid.uuid4().hex[:12]}"
                        )
                        return {
                            "success": True,
                            "message_id": message_id,
                            "status_code": response.status,
                        }

                    # Error response
                    try:
                        error_body = await response.json()
                        error_msg = (
                            error_body.get("error", {}).get("message", "")
                            or f"HTTP {response.status}"
                        )
                    except Exception:
                        error_msg = f"HTTP {response.status}"

                    result: Dict[str, Any] = {
                        "success": False,
                        "message_id": "",
                        "status_code": response.status,
                        "error": error_msg,
                    }

                    # Handle 429 rate limit
                    if response.status == 429:
                        retry_after = response.headers.get("Retry-After", "60")
                        try:
                            result["retry_after_seconds"] = float(retry_after)
                        except (ValueError, TypeError):
                            result["retry_after_seconds"] = 60.0

                    return result

        except asyncio.TimeoutError:
            raise
        except Exception as exc:
            return {
                "success": False,
                "message_id": "",
                "status_code": 0,
                "error": f"Request failed: {exc}",
            }

    # ── Private: Dry Run ──────────────────────────────────────

    def _dry_run_response(
        self,
        to: List[str],
        subject: str,
        payload: Dict[str, Any],
        reason: str,
    ) -> Dict[str, Any]:
        """Build a dry-run response (not actually sent)."""
        self._dry_run_count += 1
        dry_run_id = f"dry-run-{uuid.uuid4().hex[:12]}"

        logger.info(
            "GraphAPIEmailProvider: Dry-run send (reason=%s) to=%s subject='%s'",
            reason, to, subject[:50],
        )

        return {
            "success": True,
            "message_id": dry_run_id,
            "dry_run": True,
            "dry_run_reason": reason,
            "status_code": 0,
            "recipients": to,
            "subject": subject,
        }

    # ── Private: Large Attachment Upload ──────────────────────

    async def _upload_attachment_session(
        self,
        sender: str,
        attachment: Dict[str, Any],
    ) -> Optional[str]:
        """Upload a large attachment using a Graph API upload session.

        For attachments larger than 4MB, creates an upload session
        and uploads the file in chunks.

        Args:
            sender: Sender email for endpoint construction.
            attachment: Attachment dict with name, content_bytes, size, content_type.

        Returns:
            Attachment ID if successful, None otherwise.
        """
        file_name = attachment.get("name", "attachment")
        file_size = attachment.get("size", 0)
        content_type = attachment.get("content_type", "application/octet-stream")

        if sender:
            endpoint = f"{_GRAPH_BASE_URL}/users/{sender}/messages/attachments/createUploadSession"
        else:
            endpoint = f"{_GRAPH_BASE_URL}/me/messages/attachments/createUploadSession"

        try:
            async with self._lock:
                token = await self._token_manager.get_token(self._service_name)

            if not token.access_token or token.is_expired:
                logger.warning("GraphAPIEmailProvider: Cannot upload attachment — no valid token")
                return None

            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": token.authorization_header,
                    "Content-Type": "application/json",
                }

                # Create upload session
                upload_body = {
                    "AttachmentItem": {
                        "attachmentType": "file",
                        "name": file_name,
                        "size": file_size,
                        "contentType": content_type,
                    }
                }

                async with session.post(
                    endpoint,
                    json=upload_body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status not in (200, 201):
                        error_body = await response.json()
                        logger.warning(
                            "GraphAPIEmailProvider: Failed to create upload session: %s",
                            error_body.get("error", {}).get("message", response.status),
                        )
                        return None

                    session_data = await response.json()
                    upload_url = session_data.get("uploadUrl", "")

                if not upload_url:
                    logger.warning("GraphAPIEmailProvider: No upload URL in session response")
                    return None

                # Upload file in chunks (4 MB chunks)
                content_bytes = attachment.get("content_bytes", b"")
                chunk_size = 4 * 1024 * 1024
                offset = 0

                while offset < len(content_bytes):
                    chunk = content_bytes[offset:offset + chunk_size]
                    chunk_len = len(chunk)
                    content_range = f"bytes {offset}-{offset + chunk_len - 1}/{file_size}"

                    async with session.put(
                        upload_url,
                        data=chunk,
                        headers={
                            "Content-Length": str(chunk_len),
                            "Content-Range": content_range,
                        },
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as put_response:
                        if put_response.status not in (200, 201, 202):
                            logger.warning(
                                "GraphAPIEmailProvider: Chunk upload failed at offset %d: HTTP %d",
                                offset, put_response.status,
                            )
                            return None

                        if put_response.status in (200, 201):
                            # Upload complete
                            result = await put_response.json()
                            return result.get("id", "uploaded")

                    offset += chunk_len

                return "uploaded"

        except Exception as exc:
            logger.warning(
                "GraphAPIEmailProvider: Attachment upload session failed: %s", exc,
            )
            return None
