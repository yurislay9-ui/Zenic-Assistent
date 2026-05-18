"""Helper methods extracted from twilio_sms."""

from __future__ import annotations

import asyncio
import base64
import json
import urllib.parse
import urllib.request
import urllib.error
from ..._types import ChannelResponse, DeliveryStatus
from ..._formatter import format_sms_text, sanitize_plain_text

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


    def _dry_run_send(self, message: ChannelMessage) -> ChannelResponse:
        """Log message without sending."""
        with self._lock:
            self._sent_count += 1

        text = format_sms_text(message)
        text_preview = text[:80]
        logger.info(
            "[SMS DRY-RUN] To: %s | Text: %s%s",
            message.recipient or "default",
            text_preview,
            "..." if len(text) > 80 else "",
        )

        return ChannelResponse(
            success=True,
            channel="sms",
            status=DeliveryStatus.DRY_RUN,
            metadata={"mode": "dry_run", "char_count": len(text)},
            timestamp=time.time(),
        )


__all__ = ["TwilioSMSChannelProvider"]

