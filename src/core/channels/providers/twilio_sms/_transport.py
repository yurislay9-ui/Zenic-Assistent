"""twilio_sms — Transport mixin (API calls, webhook, dry run)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
import urllib
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from ._types import *  # noqa: F403
from ._helpers import _post_api, _post_api_aiohttp, _post_api_urllib, _dry_run_send


class TwilioSMSTransportMixin:
    """Transport methods for TwilioSMSChannelProvider."""

    # ── Internal: API ───────────────────────────────────────────

    async def _post_api(self, payload: Dict[str, str]) -> ChannelResponse:  # noqa: F821
        """POST to Twilio Messages API (form-encoded)."""
        url = _validate_url(f"{self._api_base}/Accounts/{self._account_sid}/Messages.json")  # noqa: F821

        for attempt in range(1, _MAX_RETRIES + 1):  # noqa: F821
            try:
                if _HAS_AIOHTTP and self._session:  # noqa: F821
                    return await self._post_api_aiohttp(url, payload)
                elif _HAS_URLLIB:  # noqa: F821
                    return await self._post_api_urllib(url, payload)
                else:
                    return ChannelResponse(
                        success=False, channel="sms",
                        status=DeliveryStatus.FAILED,  # noqa: F821
                        error="No HTTP library available",
                        timestamp=time.time(),
                    )
            except Exception as e:
                if attempt < _MAX_RETRIES:  # noqa: F821
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))  # noqa: F821
                    await asyncio.sleep(delay)
                else:
                    return ChannelResponse(
                        success=False, channel="sms",
                        status=DeliveryStatus.FAILED,  # noqa: F821
                        error=f"HTTP error after {_MAX_RETRIES} attempts: {e}",  # noqa: F821
                        timestamp=time.time(),
                    )

        return ChannelResponse(
            success=False, channel="sms",
            status=DeliveryStatus.FAILED,  # noqa: F821
            error="Unexpected retry loop exit",
            timestamp=time.time(),
        )

    async def _post_api_aiohttp(
        self, url: str, payload: Dict[str, str],
    ) -> ChannelResponse:
        """Send via aiohttp (form-encoded)."""
        assert self._session is not None

        async with self._session.post(url, data=payload) as resp:
            body = await resp.json()

            if resp.status in (201, 200):
                msg_sid = body.get("sid", "")
                return ChannelResponse(
                    success=True, channel="sms",
                    message_id=msg_sid,
                    status=DeliveryStatus.SENT,  # noqa: F821
                    metadata={"twilio_sid": msg_sid, "status": body.get("status", "")},
                    timestamp=time.time(),
                )
            elif resp.status == 429:
                return ChannelResponse(
                    success=False, channel="sms",
                    status=DeliveryStatus.RATE_LIMITED,  # noqa: F821
                    error=f"Rate limited: {body}",
                    timestamp=time.time(),
                )
            else:
                error_msg = body.get("message", str(body)[:200])
                return ChannelResponse(
                    success=False, channel="sms",
                    status=DeliveryStatus.FAILED,  # noqa: F821
                    error=f"Twilio API error ({resp.status}): {error_msg}",
                    timestamp=time.time(),
                )

    async def _post_api_urllib(
        self, url: str, payload: Dict[str, str],
    ) -> ChannelResponse:
        """Send via urllib (sync, wrapped in asyncio.to_thread)."""

        def _sync_post() -> ChannelResponse:
            credentials = base64.b64encode(
                f"{self._account_sid}:{self._auth_token}".encode("utf-8")
            ).decode("utf-8")

            encoded = urllib.parse.urlencode(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=encoded,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:  # noqa: F821
                    body = json.loads(resp.read().decode("utf-8"))
                    msg_sid = body.get("sid", "")
                    return ChannelResponse(
                        success=True, channel="sms",
                        message_id=msg_sid,
                        status=DeliveryStatus.SENT,  # noqa: F821
                        metadata={"twilio_sid": msg_sid},
                        timestamp=time.time(),
                    )
            except urllib.error.HTTPError as e:
                body = e.read().decode()[:300]
                if e.code == 429:
                    return ChannelResponse(
                        success=False, channel="sms",
                        status=DeliveryStatus.RATE_LIMITED,  # noqa: F821
                        error="Rate limited", timestamp=time.time(),
                    )
                return ChannelResponse(
                    success=False, channel="sms",
                    status=DeliveryStatus.FAILED,  # noqa: F821
                    error=f"HTTP {e.code}: {body}", timestamp=time.time(),
                )
            except Exception as e:
                return ChannelResponse(
                    success=False, channel="sms",
                    status=DeliveryStatus.FAILED,  # noqa: F821
                    error=f"urllib error: {e}", timestamp=time.time(),
                )

        return await asyncio.to_thread(_sync_post)
