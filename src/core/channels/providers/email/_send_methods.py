"""
ZENIC-AGENTS — Email Channel Provider: Send Methods Mixin

Contains the send() and send_confirmation() async methods, extracted
from EmailChannelProvider to keep the main module under 400 lines.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from ..._types import (
    ChannelMessage,
    ChannelResponse,
    ConfirmationRequest,
    DeliveryStatus,
)
from ._rendering import (
    build_confirmation_html,
    build_confirmation_text,
)

logger = logging.getLogger("zenic_agents.channels.email")


class _SendMixin:
    """Mixin providing send() and send_confirmation() for EmailChannelProvider.

    Expects the host class to provide:
      - is_available (property)
      - _get_executor()
      - _message_to_config()
      - _dry_run_send()
      - _dry_run_confirmation()
      - _lock
      - _sent_count, _failed_count, _confirmation_count, _dry_run_count
      - _mode, _smtp_host, _smtp_port, _smtp_user, _smtp_password
    """

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
        html_body = build_confirmation_html(request)
        text_body = build_confirmation_text(request)

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
