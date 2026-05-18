"""email — Transport mixin (send, send_confirmation, message mapping)."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, FrozenSet, List, Optional

from ._types import *  # noqa: F403
from ._helpers import (
    _render_fields_table, _build_confirmation_html,
    _build_confirmation_text, _dry_run_send, _dry_run_confirmation,
)


class EmailTransportMixin:
    """Transport methods for EmailChannelProvider (send, confirmation)."""

    # ── ChannelProvider Protocol ───────────────────────────────────

    @property
    def name(self) -> str:
        """Unique channel identifier."""
        return "email"

    @property
    def capabilities(self) -> FrozenSet[ChannelCapability]:  # noqa: F821
        """Set of capabilities this provider supports."""
        return frozenset({
            ChannelCapability.SEND_TEXT,  # noqa: F821
            ChannelCapability.SEND_RICH,  # noqa: F821
            ChannelCapability.SEND_HTML,  # noqa: F821
            ChannelCapability.SEND_FILE,  # noqa: F821
            ChannelCapability.SEND_CONFIRMATION,  # noqa: F821
        })

    @property
    def is_available(self) -> bool:
        """Whether this provider is currently operational."""
        return self._is_smtp_configured() or self._is_graph_api_configured()

    async def send(self, message: ChannelMessage) -> ChannelResponse:  # noqa: F821
        """Send an email via SMTP or Graph API.

        Never raises — always returns a ChannelResponse.
        """
        if not self.is_available:
            return self._dry_run_send(message)

        executor = self._get_executor()
        config = self._message_to_config(message)

        context: Dict[str, Any] = {"channel": "email"}
        result = await executor.execute(config, context)

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
                status=DeliveryStatus.DRY_RUN if is_dry_run else DeliveryStatus.SENT,  # noqa: F821
                metadata={
                    "mode": result.data.get("mode", self._mode),
                    "recipients": result.data.get("recipients", []),
                },
                timestamp=time.time(),
            )
        else:
            with self._lock:
                self._failed_count += 1
            if result.data.get("rate_limited"):
                status = DeliveryStatus.RATE_LIMITED  # noqa: F821
            else:
                status = DeliveryStatus.FAILED  # noqa: F821
            return ChannelResponse(
                success=False, channel="email",
                status=status, error=result.error,
                metadata=result.data, timestamp=time.time(),
            )

    async def send_confirmation(
        self, request: ConfirmationRequest,  # noqa: F821
    ) -> ChannelResponse:
        """Send a confirmation email with YES/NO/MORE_INFO action links."""
        if not self.is_available:
            return self._dry_run_confirmation(request)

        executor = self._get_executor()

        recipients = [request.recipient] if request.recipient else []
        if not recipients:
            with self._lock:
                self._failed_count += 1
            return ChannelResponse(
                success=False, channel="email",
                status=DeliveryStatus.FAILED,  # noqa: F821
                error="No recipient specified for confirmation email",
                timestamp=time.time(),
            )

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
            "channel": "email", "confirmation": True,
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
                success=True, channel="email",
                message_id=result.data.get("message_id", ""),
                status=DeliveryStatus.DRY_RUN if is_dry_run else DeliveryStatus.SENT,  # noqa: F821
                metadata={"mode": "confirmation", "action_id": request.action_id, "options": list(request.options)},
                timestamp=time.time(),
            )
        else:
            with self._lock:
                self._failed_count += 1
            return ChannelResponse(
                success=False, channel="email",
                status=DeliveryStatus.FAILED, error=result.error,  # noqa: F821
                metadata=result.data, timestamp=time.time(),
            )

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

    def _message_to_config(self, message: ChannelMessage) -> Dict[str, Any]:  # noqa: F821
        """Map a ChannelMessage to an EmailExecutor config dict."""
        recipients: List[str] = []
        if message.recipient:
            recipients.append(message.recipient)
        if message.recipients:
            recipients.extend(message.recipients)
        seen: set[str] = set()
        unique_recipients: List[str] = []
        for r in recipients:
            if r not in seen:
                seen.add(r)
                unique_recipients.append(r)

        priority_value = message.priority.value if hasattr(message.priority, "value") else str(message.priority)
        importance = _PRIORITY_TO_IMPORTANCE.get(priority_value, "normal")  # noqa: F821

        config: Dict[str, Any] = {
            "mode": self._mode,
            "to": unique_recipients,
            "subject": message.subject or message.title or "(No Subject)",
            "body": message.text,
            "html": message.html,
            "importance": importance,
        }

        if message.reply_to:
            config["reply_to"] = message.reply_to
        if message.file_url:
            config["attachments"] = [{"name": message.file_name or "attachment", "url": message.file_url}]
        if message.fields:
            fields_html = self._render_fields_table(message.fields)
            if config.get("html"):
                config["html"] = config["html"] + fields_html
            else:
                config["html"] = fields_html
        if message.title and not message.subject:
            config["subject"] = message.title
        if self._smtp_host:
            config["host"] = self._smtp_host
            config["port"] = self._smtp_port
            config["user"] = self._smtp_user
            config["password"] = self._smtp_password
        if self._smtp_user:
            config["from_email"] = self._smtp_user
        elif self._graph_from_email:
            config["from_email"] = self._graph_from_email
        if message.metadata.get("template"):
            config["template"] = message.metadata["template"]
        if message.metadata.get("template_vars"):
            config["template_vars"] = message.metadata["template_vars"]

        return config
