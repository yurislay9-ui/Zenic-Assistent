"""Helper methods extracted from email."""

from __future__ import annotations

from ..._types import ChannelMessage, ChannelResponse, ConfirmationRequest, DeliveryStatus
from ..._formatter import sanitize_html

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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

