"""
ZENIC-AGENTS — Microsoft Graph API Email Operations (Phase 2)

High-level operations: payload construction, dry-run responses,
auto-configuration, and the main send_email flow.
"""

from __future__ import annotations

import base64
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from ..oauth2 import OAuth2TokenManager, OAuth2Config, config_from_env
from ._types import (
    _HAS_AIOHTTP,
    _MAX_ATTACHMENT_SIZE_INLINE,
    _DEFAULT_SCOPES,
    _RateLimitState,
)

logger = logging.getLogger("zenic_agents.email_parts.graph_api")


# ── Payload Construction ─────────────────────────────────────────

def build_payload(
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
    """Build the Graph API sendMail request payload.

    Args:
        to: List of recipient email addresses.
        subject: Email subject line.
        body: Plain text body.
        html: HTML body (takes precedence if both body and html provided).
        cc: CC recipients.
        bcc: BCC recipients.
        sender: Sender email address.
        reply_to: Reply-to email addresses.
        importance: Email importance ("low", "normal", "high").
        attachments: List of attachment dicts.

    Returns:
        Graph API sendMail request payload dict.
    """
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


# ── Dry Run ──────────────────────────────────────────────────────

def dry_run_response(
    to: List[str],
    subject: str,
    payload: Dict[str, Any],
    reason: str,
    dry_run_count_ref: list,
) -> Dict[str, Any]:
    """Build a dry-run response (not actually sent).

    Args:
        to: Recipient email addresses.
        subject: Email subject.
        payload: The payload that would have been sent.
        reason: Reason for dry-run mode.
        dry_run_count_ref: Mutable [count] for dry-run sends.

    Returns:
        Dict with success=True, dry_run=True, etc.
    """
    dry_run_count_ref[0] += 1
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


# ── Configuration ────────────────────────────────────────────────

def auto_configure(
    service_name: str,
    from_email_ref: list,
) -> OAuth2TokenManager:
    """Auto-configure token manager from environment variables.

    Args:
        service_name: Service name in the token manager.
        from_email_ref: Mutable [from_email] to update from env.

    Returns:
        Configured OAuth2TokenManager instance.
    """
    from ..oauth2 import get_default_token_manager
    manager = get_default_token_manager()

    # Check if msgraph is already registered (get_default_token_manager auto-registers)
    token_status = manager.get_token_status(service_name)
    if not token_status.get("registered"):
        # Try to register from env
        config = config_from_env("MSGRAPH")
        if config.is_configured:
            if not config.scopes:
                config.scopes = _DEFAULT_SCOPES
            manager.register_service(service_name, config)

    # Read default from_email from env
    if not from_email_ref[0]:
        from_email_ref[0] = os.environ.get("MSGRAPH_FROM_EMAIL", "")

    return manager


def is_configured(
    token_manager: OAuth2TokenManager,
    service_name: str,
) -> bool:
    """Check if we have the minimum configuration to send emails.

    Args:
        token_manager: OAuth2TokenManager instance.
        service_name: Service name in the token manager.

    Returns:
        True if the provider is configured for actual sending.
    """
    token_status = token_manager.get_token_status(service_name)
    return token_status.get("configured", False)


# ── Main Send Flow ───────────────────────────────────────────────

async def send_email(
    provider: Any,
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

    Orchestrates the full send flow: validation, payload construction,
    dry-run checks, and retry-based sending.

    Args:
        provider: GraphAPIEmailProvider instance.
        to: List of recipient email addresses.
        subject: Email subject line.
        body: Plain text body.
        html: HTML body (takes precedence if both body and html provided).
        cc: CC recipients.
        bcc: BCC recipients.
        from_email: Sender email (overrides default).
        attachments: List of attachment dicts.
        reply_to: Reply-to email addresses.
        importance: Email importance ("low", "normal", "high").

    Returns:
        Dict with success, message_id, dry_run, status_code, error, etc.
    """
    from ._client import send_with_retry

    start = time.monotonic()

    # Validate importance
    valid_importance = {"low", "normal", "high"}
    if importance not in valid_importance:
        importance = "normal"

    # Determine sender
    sender = from_email or provider._from_email

    # Build the Graph API request payload
    payload = build_payload(
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
    if not provider._is_configured():
        return dry_run_response(
            to=to, subject=subject, payload=payload,
            reason="service_not_configured",
            dry_run_count_ref=provider._dry_run_count_ref,
        )

    if not _HAS_AIOHTTP:
        return dry_run_response(
            to=to, subject=subject, payload=payload,
            reason="aiohttp_not_available",
            dry_run_count_ref=provider._dry_run_count_ref,
        )

    # Send with retry
    result = await send_with_retry(
        provider=provider,
        payload=payload,
        sender=sender,
        service_name=provider._service_name,
        token_manager=provider._token_manager,
        rate_limit=provider._rate_limit,
        send_count_ref=provider._send_count_ref,
        error_count_ref=provider._error_count_ref,
    )

    elapsed = round((time.monotonic() - start) * 1000, 2)
    result["duration_ms"] = elapsed
    result["recipients"] = to
    result["subject"] = subject

    return result
