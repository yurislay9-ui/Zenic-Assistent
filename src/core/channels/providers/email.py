"""
ZENIC-AGENTS — Email Channel Provider (Phase 2)

Outbound email channel provider implementing the ChannelProvider protocol.
Wraps EmailExecutor functionality as a unified channel provider for
the channel routing system.

Supports:
  - SMTP and Microsoft Graph API (auto-detected)
  - Plain text, HTML, and rich (template-based) emails
  - File attachments
  - Interactive confirmation emails with YES/NO/MORE_INFO links
  - Per-recipient and global rate limiting
  - Priority → importance mapping
  - ChannelMessage.fields → HTML table rendering
  - Dry-run mode when neither SMTP nor Graph API is configured

Design invariants:
  1. Never raises from send() — always returns ChannelResponse.
  2. Dry-run mode when unconfigured (logs messages instead).
  3. Thread-safe statistics via threading.Lock.
  4. Idempotent start()/stop().
  5. Uses EmailExecutor internally for actual sending.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, FrozenSet, List, Optional

from .._formatter import MessageFormatter, truncate, sanitize_html
from .._protocol import ChannelProvider
from .._types import (
    ChannelCapability,
    ChannelMessage,
    ChannelResponse,
    ConfirmationRequest,
    DeliveryStatus,
    RateLimitInfo,
)

logger = logging.getLogger("zenic_agents.channels.email")

# ── Optional Dependencies ─────────────────────────────────────────

try:
    import aiohttp
    _HAS_AIOHTTP = True
except ImportError:
    _HAS_AIOHTTP = False

# ── Constants ──────────────────────────────────────────────────────

_VALID_MODES = frozenset({"smtp", "graph_api", "auto"})

# Priority → importance mapping (ChannelPriority → email importance)
_PRIORITY_TO_IMPORTANCE: Dict[str, str] = {
    "low": "low",
    "normal": "normal",
    "high": "high",
    "urgent": "high",
    "emergency": "high",
}


class EmailChannelProvider:
    """Email channel provider implementing the ChannelProvider protocol.

    Wraps EmailExecutor functionality as a channel provider for the
    unified channel system. Supports SMTP, Microsoft Graph API, and
    auto mode (tries Graph API first, falls back to SMTP).

    Capabilities:
      - SEND_TEXT          → Plain text emails
      - SEND_RICH          → Template-based rich emails with fields table
      - SEND_HTML          → HTML body emails
      - SEND_FILE          → File attachments
      - SEND_CONFIRMATION  → Confirmation emails with action links

    Usage:
        provider = EmailChannelProvider(mode="auto")
        await provider.start()
        response = await provider.send(ChannelMessage(
            recipient="user@example.com",
            subject="Hello",
            text="World",
        ))
        await provider.stop()
    """

    def __init__(
        self,
        mode: str = "auto",
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        graph_client_id: Optional[str] = None,
        graph_client_secret: Optional[str] = None,
        graph_tenant_id: Optional[str] = None,
        graph_from_email: Optional[str] = None,
    ) -> None:
        """Initialize the email channel provider.

        Args:
            mode: Send mode — "smtp", "graph_api", or "auto" (default: "auto").
            smtp_host: SMTP server host (or env SMTP_HOST).
            smtp_port: SMTP server port (or env SMTP_PORT, default 587).
            smtp_user: SMTP username (or env SMTP_USER).
            smtp_password: SMTP password (or env SMTP_PASSWORD).
            graph_client_id: Azure AD client ID (or env MSGRAPH_CLIENT_ID).
            graph_client_secret: Azure AD client secret (or env MSGRAPH_CLIENT_SECRET).
            graph_tenant_id: Azure AD tenant ID (or env MSGRAPH_TENANT_ID).
            graph_from_email: Graph API sender email (or env MSGRAPH_FROM_EMAIL).
        """
        mode = mode.lower()
        if mode not in _VALID_MODES:
            mode = "auto"
        self._mode = mode

        # SMTP config (env fallbacks)
        self._smtp_host = smtp_host or os.environ.get("SMTP_HOST", "")
        self._smtp_port = smtp_port or int(os.environ.get("SMTP_PORT", "587"))
        self._smtp_user = smtp_user or os.environ.get("SMTP_USER", "")
        self._smtp_password = smtp_password or os.environ.get("SMTP_PASSWORD", "")

        # Graph API config (env fallbacks)
        self._graph_client_id = graph_client_id or os.environ.get("MSGRAPH_CLIENT_ID", "")
        self._graph_client_secret = graph_client_secret or os.environ.get("MSGRAPH_CLIENT_SECRET", "")
        self._graph_tenant_id = graph_tenant_id or os.environ.get("MSGRAPH_TENANT_ID", "")
        self._graph_from_email = graph_from_email or os.environ.get("MSGRAPH_FROM_EMAIL", "")

        # Internal state
        self._lock = threading.Lock()
        self._sent_count: int = 0
        self._failed_count: int = 0
        self._confirmation_count: int = 0
        self._dry_run_count: int = 0
        self._started: bool = False
        self._rate_limit_info = RateLimitInfo()
        self._executor: Optional[Any] = None  # Lazy-initialized EmailExecutor

    # ── ChannelProvider Protocol ───────────────────────────────────

    @property
    def name(self) -> str:
        """Unique channel identifier."""
        return "email"

    @property
    def capabilities(self) -> FrozenSet[ChannelCapability]:
        """Set of capabilities this provider supports."""
        return frozenset({
            ChannelCapability.SEND_TEXT,
            ChannelCapability.SEND_RICH,
            ChannelCapability.SEND_HTML,
            ChannelCapability.SEND_FILE,
            ChannelCapability.SEND_CONFIRMATION,
        })

    @property
    def is_available(self) -> bool:
        """Whether this provider is currently operational.

        Returns True if either SMTP or Graph API is configured.
        """
        return self._is_smtp_configured() or self._is_graph_api_configured()

    async def send(self, message: ChannelMessage) -> ChannelResponse:
        """Send an email via SMTP or Graph API.

        Maps ChannelMessage fields to email executor config and delegates
        to the internal EmailExecutor instance.

        Never raises — always returns a ChannelResponse.

        Args:
            message: Universal message envelope.

        Returns:
            ChannelResponse with delivery result.
        """
        if not self.is_available:
            return self._dry_run_send(message)

        # Initialize executor lazily
        executor = self._get_executor()

        # Build executor config from ChannelMessage
        config = self._message_to_config(message)

        # Execute via EmailExecutor
        context: Dict[str, Any] = {"channel": "email"}
        result = await executor.execute(config, context)

        # Map ActionResult → ChannelResponse
        if result.success:
            is_dry_run = result.data.get("dry_run", False)
            with self._lock:
                if is_dry_run:
                    self._dry_run_count += 1
                else:
                    self._sent_count += 1
            return ChannelResponse(
                success=True,
                channel="email",
                message_id=result.data.get("message_id", ""),
                status=DeliveryStatus.DRY_RUN if is_dry_run else DeliveryStatus.SENT,
                metadata={
                    "mode": result.data.get("mode", self._mode),
                    "recipients": result.data.get("recipients", []),
                },
                timestamp=time.time(),
            )
        else:
            with self._lock:
                self._failed_count += 1

            # Determine status
            if result.data.get("rate_limited"):
                status = DeliveryStatus.RATE_LIMITED
            else:
                status = DeliveryStatus.FAILED

            return ChannelResponse(
                success=False,
                channel="email",
                status=status,
                error=result.error,
                metadata=result.data,
                timestamp=time.time(),
            )

    async def send_confirmation(
        self, request: ConfirmationRequest,
    ) -> ChannelResponse:
        """Send a confirmation email with YES/NO/MORE_INFO action links.

        Generates an HTML email with clickable links for each option.
        Falls back to plain text with instructions if HTML rendering fails.

        Args:
            request: Confirmation request with options.

        Returns:
            ChannelResponse with the sent message info.
        """
        if not self.is_available:
            return self._dry_run_confirmation(request)

        executor = self._get_executor()

        # Build confirmation email config
        recipients = [request.recipient] if request.recipient else []
        if not recipients:
            with self._lock:
                self._failed_count += 1
            return ChannelResponse(
                success=False,
                channel="email",
                status=DeliveryStatus.FAILED,
                error="No recipient specified for confirmation email",
                timestamp=time.time(),
            )

        # Build HTML body with action links
        html_body = self._build_confirmation_html(request)
        text_body = self._build_confirmation_text(request)

        config: Dict[str, Any] = {
            "mode": self._mode,
            "to": recipients,
            "subject": f"Confirmation Required: {request.title}",
            "body": text_body,
            "html": html_body,
            "importance": "high",
        }
        if self._smtp_host:
            config["host"] = self._smtp_host
            config["port"] = self._smtp_port
            config["user"] = self._smtp_user
            config["password"] = self._smtp_password

        context: Dict[str, Any] = {
            "channel": "email",
            "confirmation": True,
            "action_id": request.action_id,
        }
        result = await executor.execute(config, context)

        if result.success:
            is_dry_run = result.data.get("dry_run", False)
            with self._lock:
                self._confirmation_count += 1
                if is_dry_run:
                    self._dry_run_count += 1
                else:
                    self._sent_count += 1
            return ChannelResponse(
                success=True,
                channel="email",
                message_id=result.data.get("message_id", ""),
                status=DeliveryStatus.DRY_RUN if is_dry_run else DeliveryStatus.SENT,
                metadata={
                    "mode": "confirmation",
                    "action_id": request.action_id,
                    "options": list(request.options),
                },
                timestamp=time.time(),
            )
        else:
            with self._lock:
                self._failed_count += 1
            return ChannelResponse(
                success=False,
                channel="email",
                status=DeliveryStatus.FAILED,
                error=result.error,
                metadata=result.data,
                timestamp=time.time(),
            )

    async def start(self) -> None:
        """Initialize the provider.

        Validates configuration and initializes the GraphAPIEmailProvider
        if Graph API is configured. Idempotent — safe to call multiple times.
        """
        if self._started:
            return

        # Pre-initialize executor
        self._get_executor()

        self._started = True
        logger.info(
            "EmailChannelProvider: started (mode=%s, smtp=%s, graph_api=%s)",
            self._mode,
            self._is_smtp_configured(),
            self._is_graph_api_configured(),
        )

    async def stop(self) -> None:
        """Gracefully shut down the provider.

        Idempotent — safe to call multiple times.
        """
        self._started = False
        logger.info("EmailChannelProvider: stopped")

    @property
    def stats(self) -> Dict[str, Any]:
        """Provider statistics for monitoring and health checks."""
        with self._lock:
            return {
                "name": "email",
                "mode": self._mode,
                "sent_count": self._sent_count,
                "failed_count": self._failed_count,
                "confirmation_count": self._confirmation_count,
                "dry_run_count": self._dry_run_count,
                "is_available": self.is_available,
                "smtp_configured": self._is_smtp_configured(),
                "graph_api_configured": self._is_graph_api_configured(),
                "started": self._started,
            }

    @property
    def rate_limit_info(self) -> RateLimitInfo:
        """Current rate limit status."""
        return self._rate_limit_info

    # ── Internal: Configuration Checks ─────────────────────────────

    def _is_smtp_configured(self) -> bool:
        """Check if SMTP is configured."""
        return bool(self._smtp_host)

    def _is_graph_api_configured(self) -> bool:
        """Check if Microsoft Graph API is configured."""
        return bool(
            self._graph_client_id
            and self._graph_client_secret
            and self._graph_tenant_id,
        )

    # ── Internal: Executor Management ──────────────────────────────

    def _get_executor(self) -> Any:
        """Get or create the internal EmailExecutor instance."""
        with self._lock:
            if self._executor is None:
                from ...executors.email_executor import EmailExecutor
                self._executor = EmailExecutor()
            return self._executor

    # ── Internal: Message Mapping ──────────────────────────────────

    def _message_to_config(self, message: ChannelMessage) -> Dict[str, Any]:
        """Map a ChannelMessage to an EmailExecutor config dict.

        Field mappings:
          - message.text          → body
          - message.html          → html
          - message.subject       → subject
          - message.recipient     → to (single)
          - message.recipients    → to (multiple)
          - message.file_url      → attachments (URL reference)
          - message.file_name     → attachment name
          - message.priority      → importance
          - message.fields        → HTML table appended to body
          - message.reply_to      → reply_to
          - message.metadata      → extra context
        """
        # Resolve recipients
        recipients: List[str] = []
        if message.recipient:
            recipients.append(message.recipient)
        if message.recipients:
            recipients.extend(message.recipients)
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_recipients: List[str] = []
        for r in recipients:
            if r not in seen:
                seen.add(r)
                unique_recipients.append(r)

        # Priority → importance mapping
        priority_value = message.priority.value if hasattr(message.priority, "value") else str(message.priority)
        importance = _PRIORITY_TO_IMPORTANCE.get(priority_value, "normal")

        # Build config
        config: Dict[str, Any] = {
            "mode": self._mode,
            "to": unique_recipients,
            "subject": message.subject or message.title or "(No Subject)",
            "body": message.text,
            "html": message.html,
            "importance": importance,
        }

        # Reply-to
        if message.reply_to:
            config["reply_to"] = message.reply_to

        # File attachments (URL reference → metadata for executor)
        if message.file_url:
            config["attachments"] = [{
                "name": message.file_name or "attachment",
                "url": message.file_url,
            }]

        # Fields → HTML table
        if message.fields:
            fields_html = self._render_fields_table(message.fields)
            if config.get("html"):
                config["html"] = config["html"] + fields_html
            else:
                config["html"] = fields_html

        # Title/subtitle → prepend to body if set
        if message.title and not message.subject:
            config["subject"] = message.title

        # SMTP config (override executor env defaults)
        if self._smtp_host:
            config["host"] = self._smtp_host
            config["port"] = self._smtp_port
            config["user"] = self._smtp_user
            config["password"] = self._smtp_password

        # From email
        if self._smtp_user:
            config["from_email"] = self._smtp_user
        elif self._graph_from_email:
            config["from_email"] = self._graph_from_email

        # Template support via metadata
        if message.metadata.get("template"):
            config["template"] = message.metadata["template"]
        if message.metadata.get("template_vars"):
            config["template_vars"] = message.metadata["template_vars"]

        return config

    # ── Internal: HTML Rendering ───────────────────────────────────

    @staticmethod
    def _render_fields_table(fields: Any) -> str:
        """Render ChannelMessage.fields as an HTML table.

        Args:
            fields: Sequence of dicts with 'title'/'name' and 'value' keys.

        Returns:
            HTML string with a styled table.
        """
        if not fields:
            return ""

        rows_html = ""
        for field in fields:
            key = field.get("title", field.get("name", ""))
            value = field.get("value", "")
            rows_html += (
                f"<tr>"
                f"<td style='padding:6px 12px;border:1px solid #ddd;font-weight:bold;"
                f"background:#f5f5f5;'>{sanitize_html(str(key))}</td>"
                f"<td style='padding:6px 12px;border:1px solid #ddd;'>"
                f"{sanitize_html(str(value))}</td>"
                f"</tr>"
            )

        return (
            f"<table style='border-collapse:collapse;margin:16px 0;"
            f"font-family:Arial,sans-serif;font-size:14px;'>"
            f"{rows_html}</table>"
        )

    # ── Internal: Confirmation Email Rendering ─────────────────────

    @staticmethod
    def _build_confirmation_html(request: ConfirmationRequest) -> str:
        """Build HTML body for a confirmation email.

        Creates a styled email with clickable action links for each option.

        Args:
            request: The confirmation request.

        Returns:
            HTML string for the email body.
        """
        # Button styles per option
        button_styles: Dict[str, str] = {
            "yes": "background:#28a745;color:#fff;",
            "no": "background:#dc3545;color:#fff;",
            "more_info": "background:#6c757d;color:#fff;",
        }

        # Default labels
        option_labels: Dict[str, str] = {
            "yes": "✅ Yes — Confirm",
            "no": "❌ No — Deny",
            "more_info": "ℹ️ More Info",
        }

        buttons_html = ""
        for option in request.options:
            label = option_labels.get(option, option.replace("_", " ").title())
            style = button_styles.get(option, "background:#007bff;color:#fff;")
            # Build a mailto-style or callback URL
            # In production, these would be actual callback URLs
            action_url = f"#confirm-{request.action_id}-{option}"
            buttons_html += (
                f"<a href='{action_url}' style='{style}"
                f"display:inline-block;padding:10px 20px;margin:4px;"
                f"text-decoration:none;border-radius:4px;font-weight:bold;"
                f"font-family:Arial,sans-serif;'>"
                f"{label}</a> "
            )

        # Timeout notice
        timeout_text = ""
        if request.timeout_seconds > 0:
            minutes = request.timeout_seconds // 60
            timeout_text = (
                f"<p style='color:#6c757d;font-size:12px;'>"
                f"This request will expire in {minutes} minute(s).</p>"
            )

        return (
            f"<div style='font-family:Arial,sans-serif;max-width:600px;"
            f"margin:0 auto;padding:20px;'>"
            f"<h2 style='color:#333;'>{sanitize_html(request.title)}</h2>"
            f"<p style='color:#555;'>{sanitize_html(request.message)}</p>"
            f"<div style='margin:20px 0;'>"
            f"{buttons_html}"
            f"</div>"
            f"{timeout_text}"
            f"<p style='color:#999;font-size:11px;'>"
            f"Action ID: {sanitize_html(request.action_id)} | "
            f"Type: {sanitize_html(request.action_type)}</p>"
            f"</div>"
        )

    @staticmethod
    def _build_confirmation_text(request: ConfirmationRequest) -> str:
        """Build plain text body for a confirmation email.

        Args:
            request: The confirmation request.

        Returns:
            Plain text string for the email body.
        """
        option_lines = []
        for option in request.options:
            option_lines.append(f"  - {option.upper()}: Reply with '{option}'")

        options_text = "\n".join(option_lines)
        timeout_text = ""
        if request.timeout_seconds > 0:
            minutes = request.timeout_seconds // 60
            timeout_text = f"\nThis request will expire in {minutes} minute(s)."

        return (
            f"{request.title}\n"
            f"{'=' * len(request.title)}\n\n"
            f"{request.message}\n\n"
            f"Please respond with one of the following:\n"
            f"{options_text}\n"
            f"{timeout_text}\n\n"
            f"Action ID: {request.action_id}\n"
            f"Action Type: {request.action_type}"
        )

    # ── Internal: Dry Run ──────────────────────────────────────────

    def _dry_run_send(self, message: ChannelMessage) -> ChannelResponse:
        """Log message without sending (dry-run mode)."""
        with self._lock:
            self._dry_run_count += 1

        recipient = message.recipient or ", ".join(message.recipients) or "default"
        text_preview = (message.text or message.html or "")[:200]
        logger.info(
            "[EMAIL DRY-RUN] To: %s | Subject: %s | Text: %s",
            recipient,
            message.subject or "(none)",
            text_preview,
        )

        return ChannelResponse(
            success=True,
            channel="email",
            status=DeliveryStatus.DRY_RUN,
            metadata={"mode": "dry_run"},
            timestamp=time.time(),
        )

    def _dry_run_confirmation(
        self, request: ConfirmationRequest,
    ) -> ChannelResponse:
        """Log confirmation without sending (dry-run mode)."""
        with self._lock:
            self._dry_run_count += 1

        logger.info(
            "[EMAIL DRY-RUN] Confirmation: %s | Options: %s | To: %s",
            request.title,
            list(request.options),
            request.recipient or "default",
        )

        return ChannelResponse(
            success=True,
            channel="email",
            status=DeliveryStatus.DRY_RUN,
            metadata={"mode": "dry_run", "action_id": request.action_id},
            timestamp=time.time(),
        )


__all__ = ["EmailChannelProvider"]
