"""
ZENIC-AGENTS — Email Composer Module (Phase 2)

Message composition, recipient resolution, and dry-run result building
for the EmailExecutor.
"""

from __future__ import annotations

import email.encoders
import email.mime.multipart
import email.mime.text
import email.mime.base
import email.utils
import logging
import uuid
from typing import Any, Dict, List, Optional

from ..base import ActionResult

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


def build_mime_message(
    from_email: str,
    recipients: List[str],
    subject: str,
    body: str,
    html: str,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    reply_to: str = "",
    importance: str = "normal",
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> email.mime.multipart.MIMEMultipart:
    """Build a MIME message for SMTP sending."""
    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["From"] = from_email
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    if cc:
        msg["Cc"] = ", ".join(cc)
    if reply_to:
        msg["Reply-To"] = reply_to
    if importance and importance != "normal":
        msg["X-Priority"] = {"low": "5", "high": "1"}.get(importance, "3")
        msg["Importance"] = importance

    msg["Message-ID"] = email.utils.make_msgid(domain=from_email.split("@")[-1] if "@" in from_email else "localhost")

    # Attach text and HTML parts
    if body:
        msg.attach(email.mime.text.MIMEText(body, "plain", "utf-8"))
    if html:
        msg.attach(email.mime.text.MIMEText(html, "html", "utf-8"))

    # If neither body nor html, attach empty text
    if not body and not html:
        msg.attach(email.mime.text.MIMEText(" ", "plain", "utf-8"))

    # Attachments
    for att in (attachments or []):
        part = email.mime.base.MIMEBase(
            "application", att.get("content_type", "octet-stream"),
        )
        content = att.get("content_bytes", b"")
        if isinstance(content, str):
            content = content.encode("utf-8")
        part.set_payload(content)
        email.encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{att.get("name", "attachment")}"',
        )
        msg.attach(part)

    return msg


def resolve_recipients(config: Dict[str, Any]) -> List[str]:
    """Resolve recipients from config, normalizing to a list."""
    to = config.get("to", [])
    if isinstance(to, str):
        return [to.strip()] if to.strip() else []
    if isinstance(to, (list, tuple)):
        return [r.strip() for r in to if r and r.strip()]
    return []


def build_dry_run_result(
    recipients: List[str],
    subject: str,
    reason: str,
) -> ActionResult:
    """Build a dry-run ActionResult."""
    dry_run_id = f"dry-run-{uuid.uuid4().hex[:12]}"
    logger.info(
        "EmailExecutor: Dry-run (reason=%s) to=%s subject='%s'",
        reason, recipients, subject[:50],
    )
    return ActionResult(
        True,
        {
            "mode": "dry_run",
            "recipients": recipients,
            "subject": subject,
            "dry_run": True,
            "dry_run_reason": reason,
            "message_id": dry_run_id,
        },
    )


__all__ = [
    "build_mime_message",
    "resolve_recipients",
    "build_dry_run_result",
    "_HAS_AIOSMTPLIB_LOCAL",
    "_HAS_URLLIB",
    "_VALID_MODES",
    "_VALID_IMPORTANCE",
    "_SMTP_TIMEOUT",
]
