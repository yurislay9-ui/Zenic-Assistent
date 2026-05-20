"""Helper methods extracted from whatsapp."""

from __future__ import annotations

import asyncio
import json
import urllib.request
import urllib.error
from ..._types import ChannelResponse, DeliveryStatus
from ..._formatter import format_whatsapp_text, truncate, build_whatsapp_interactive_buttons

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


    def _build_media_payload(
        self,
        message: ChannelMessage,
        media_type: str,
        media_url: str,
    ) -> Dict[str, Any]:
        """Build a WhatsApp media message payload."""
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": message.recipient,
            "type": media_type,
            media_type: {
                "link": media_url,
            },
        }

        # Add caption for images/documents
        if message.text:
            caption = truncate(message.text, 1024)
            payload[media_type]["caption"] = caption

        # Add filename for documents
        if media_type == "document" and message.file_name:
            payload[media_type]["filename"] = message.file_name

        return payload

    async def _post_api(self, payload: Dict[str, Any]) -> ChannelResponse:
        """POST to WhatsApp Cloud API."""
        url = f"{self._api_base}/{self._phone_number_id}/messages"

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                if _HAS_AIOHTTP and self._session:
                    return await self._post_api_aiohttp(url, payload)
                elif _HAS_URLLIB:
                    return await self._post_api_urllib(url, payload)
                else:
                    return ChannelResponse(
                        success=False,
                        channel="whatsapp",
                        status=DeliveryStatus.FAILED,
                        error="No HTTP library available",
                        timestamp=time.time(),
                    )
            except Exception as e:
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    import asyncio
                    await asyncio.sleep(delay)
                else:
                    return ChannelResponse(
                        success=False,
                        channel="whatsapp",
                        status=DeliveryStatus.FAILED,
                        error=f"HTTP error after {_MAX_RETRIES} attempts: {e}",
                        timestamp=time.time(),
                    )

        return ChannelResponse(
            success=False, channel="whatsapp",
            status=DeliveryStatus.FAILED,
            error="Unexpected retry loop exit",
            timestamp=time.time(),
        )

    async def _post_api_aiohttp(
        self, url: str, payload: Dict[str, Any],
    ) -> ChannelResponse:
        """Send via aiohttp."""
        assert self._session is not None

        async with self._session.post(url, json=payload) as resp:
            body = await resp.json()

            # Track rate limits
            remaining = resp.headers.get("X-App-Usage")
            if remaining:
                try:
                    usage = json.loads(remaining)
                    self._rate_limit_info = RateLimitInfo(
                        remaining=max(0, 100 - usage.get("call_count", 0)),
                    )
                except (json.JSONDecodeError, TypeError):
                    pass

            if resp.status == 200:
                messages = body.get("messages", [{}])
                msg_id = messages[0].get("id", "") if messages else ""
                return ChannelResponse(
                    success=True,
                    channel="whatsapp",
                    message_id=msg_id,
                    status=DeliveryStatus.SENT,
                    metadata={"whatsapp_message_id": msg_id},
                    timestamp=time.time(),
                )
            elif resp.status == 429:
                return ChannelResponse(
                    success=False,
                    channel="whatsapp",
                    status=DeliveryStatus.RATE_LIMITED,
                    error=f"Rate limited: {body}",
                    timestamp=time.time(),
                )
            else:
                error = body.get("error", {})
                return ChannelResponse(
                    success=False,
                    channel="whatsapp",
                    status=DeliveryStatus.FAILED,
                    error=f"WhatsApp API error: {error.get('message', str(body)[:200])}",
                    timestamp=time.time(),
                )

    async def _post_api_urllib(
        self, url: str, payload: Dict[str, Any],
    ) -> ChannelResponse:
        """Send via urllib (sync, wrapped in asyncio.to_thread)."""
        import asyncio

        validated_url = _validate_url(url)

        def _sync_post() -> ChannelResponse:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                validated_url,
                data=data,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    messages = body.get("messages", [{}])
                    msg_id = messages[0].get("id", "") if messages else ""
                    return ChannelResponse(
                        success=True,
                        channel="whatsapp",
                        message_id=msg_id,
                        status=DeliveryStatus.SENT,
                        metadata={"whatsapp_message_id": msg_id},
                        timestamp=time.time(),
                    )
            except urllib.error.HTTPError as e:
                body = e.read().decode()[:300]
                if e.code == 429:
                    return ChannelResponse(
                        success=False,
                        channel="whatsapp",
                        status=DeliveryStatus.RATE_LIMITED,
                        error=f"Rate limited",
                        timestamp=time.time(),
                    )
                return ChannelResponse(
                    success=False,
                    channel="whatsapp",
                    status=DeliveryStatus.FAILED,
                    error=f"HTTP {e.code}: {body}",
                    timestamp=time.time(),
                )
            except Exception as e:
                return ChannelResponse(
                    success=False,
                    channel="whatsapp",
                    status=DeliveryStatus.FAILED,
                    error=f"urllib error: {e}",
                    timestamp=time.time(),
                )

        return await asyncio.to_thread(_sync_post)

    # ── Internal: Dry Run ───────────────────────────────────────


    def _dry_run_send(self, message: ChannelMessage) -> ChannelResponse:
        """Log message without sending."""
        with self._lock:
            self._sent_count += 1

        text_preview = (message.text or "")[:200]
        logger.info(
            "[WHATSAPP DRY-RUN] To: %s | Text: %s",
            message.recipient or "default",
            text_preview,
        )

        return ChannelResponse(
            success=True,
            channel="whatsapp",
            status=DeliveryStatus.DRY_RUN,
            metadata={"mode": "dry_run"},
            timestamp=time.time(),
        )


    def _dry_run_confirmation(
        self, request: ConfirmationRequest,
    ) -> ChannelResponse:
        """Log confirmation without sending."""
        with self._lock:
            self._confirmation_count += 1

        logger.info(
            "[WHATSAPP DRY-RUN] Confirmation: %s | Options: %s",
            request.title,
            list(request.options),
        )

        return ChannelResponse(
            success=True,
            channel="whatsapp",
            status=DeliveryStatus.DRY_RUN,
            metadata={"mode": "dry_run", "action_id": request.action_id},
            timestamp=time.time(),
        )


__all__ = ["WhatsAppChannelProvider"]

