"""
ZENIC-AGENTS — Push Channel Provider: FCM HTTP Mixin

Firebase Cloud Messaging HTTP v1 API request methods.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

from ..._types import (
    ChannelResponse,
    DeliveryStatus,
    RateLimitInfo,
)
from ._utils import (
    _HAS_AIOHTTP,
    _HAS_URLLIB,
    _FCM_BASE_URL,
    _MAX_RETRIES,
    _RETRY_BASE_DELAY,
    _HTTP_TIMEOUT,
    _validate_url,
)

logger = logging.getLogger("zenic_agents.channels.push")


class _FcmHttpMixin:
    """Mixin for FCM HTTP request methods."""

    async def _post_fcm(
        self, payload: Dict[str, Any],
    ) -> ChannelResponse:
        """POST a message to the FCM HTTP v1 API.

        Args:
            payload: FCM message payload.

        Returns:
            ChannelResponse with delivery result.
        """
        access_token = await self._get_fcm_access_token()
        if not access_token:
            return ChannelResponse(
                success=False,
                channel="push",
                status=DeliveryStatus.FAILED,
                error="Failed to obtain FCM access token",
                timestamp=time.time(),
            )

        url = _FCM_BASE_URL.format(project_id=self._fcm_project_id)
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                if _HAS_AIOHTTP and self._session:
                    return await self._post_fcm_aiohttp(url, data, headers)
                elif _HAS_URLLIB:
                    return await self._post_fcm_urllib(url, data, headers)
                else:
                    return ChannelResponse(
                        success=False,
                        channel="push",
                        status=DeliveryStatus.FAILED,
                        error="No HTTP library available",
                        timestamp=time.time(),
                    )
            except Exception as e:
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "PushChannelProvider: FCM attempt %d/%d failed: %s "
                        "— retrying in %.1fs",
                        attempt, _MAX_RETRIES, e, delay,
                    )
                    import asyncio
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "PushChannelProvider: FCM all %d attempts failed: %s",
                        _MAX_RETRIES, e,
                    )
                    return ChannelResponse(
                        success=False,
                        channel="push",
                        status=DeliveryStatus.FAILED,
                        error=f"FCM HTTP error after {_MAX_RETRIES} attempts: {e}",
                        timestamp=time.time(),
                    )

        return ChannelResponse(
            success=False,
            channel="push",
            status=DeliveryStatus.FAILED,
            error="Unexpected FCM retry loop exit",
            timestamp=time.time(),
        )

    async def _post_fcm_aiohttp(
        self, url: str, data: bytes, headers: Dict[str, str],
    ) -> ChannelResponse:
        """Send FCM message via aiohttp."""
        assert self._session is not None

        async with self._session.post(url, data=data, headers=headers) as resp:
            body = await resp.text()

            # Track rate limits
            self._update_rate_limit_from_headers(resp.headers)

            if resp.status == 200:
                try:
                    resp_data = json.loads(body)
                except json.JSONDecodeError:
                    resp_data = {}

                msg_name = resp_data.get("name", "")

                return ChannelResponse(
                    success=True,
                    channel="push",
                    message_id=msg_name,
                    status=DeliveryStatus.SENT,
                    metadata={
                        "backend": "fcm",
                        "http_status": resp.status,
                        "message_name": msg_name,
                    },
                    timestamp=time.time(),
                )
            elif resp.status == 429:
                retry_after = float(
                    resp.headers.get("Retry-After", "5"),
                )
                self._rate_limit_info = RateLimitInfo(
                    remaining=0,
                    reset_at=time.time() + retry_after,
                )
                return ChannelResponse(
                    success=False,
                    channel="push",
                    status=DeliveryStatus.RATE_LIMITED,
                    error=f"FCM rate limited. Retry after {retry_after}s",
                    timestamp=time.time(),
                )
            else:
                return ChannelResponse(
                    success=False,
                    channel="push",
                    status=DeliveryStatus.FAILED,
                    error=f"FCM HTTP {resp.status}: {body[:300]}",
                    metadata={"backend": "fcm", "http_status": resp.status},
                    timestamp=time.time(),
                )

    async def _post_fcm_urllib(
        self, url: str, data: bytes, headers: Dict[str, str],
    ) -> ChannelResponse:
        """Send FCM message via urllib (sync, wrapped in asyncio.to_thread)."""
        import asyncio
        import urllib.request
        import urllib.error

        validated_url = _validate_url(url)

        def _sync_post() -> ChannelResponse:
            req = urllib.request.Request(
                validated_url, data=data, headers=headers, method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    try:
                        resp_data = json.loads(body)
                    except json.JSONDecodeError:
                        resp_data = {}

                    msg_name = resp_data.get("name", "")
                    return ChannelResponse(
                        success=True,
                        channel="push",
                        message_id=msg_name,
                        status=DeliveryStatus.SENT,
                        metadata={
                            "backend": "fcm",
                            "http_status": resp.status,
                            "message_name": msg_name,
                        },
                        timestamp=time.time(),
                    )
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")[:300]
                if e.code == 429:
                    return ChannelResponse(
                        success=False,
                        channel="push",
                        status=DeliveryStatus.RATE_LIMITED,
                        error="FCM rate limited",
                        timestamp=time.time(),
                    )
                return ChannelResponse(
                    success=False,
                    channel="push",
                    status=DeliveryStatus.FAILED,
                    error=f"FCM HTTP {e.code}: {body}",
                    metadata={"backend": "fcm", "http_status": e.code},
                    timestamp=time.time(),
                )
            except Exception as e:
                return ChannelResponse(
                    success=False,
                    channel="push",
                    status=DeliveryStatus.FAILED,
                    error=f"FCM urllib error: {e}",
                    timestamp=time.time(),
                )

        return await asyncio.to_thread(_sync_post)

    async def _http_post_form(
        self, url: str, data: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        """POST form-encoded data and return parsed JSON response.

        Used for OAuth2 token exchange.

        Args:
            url: Target URL.
            data: Form-encoded POST data.

        Returns:
            Dict with 'success', 'body', 'status' or None on failure.
        """
        import asyncio
        import urllib.request
        import urllib.error
        import urllib.parse

        encoded = urllib.parse.urlencode(data).encode("utf-8") if _HAS_URLLIB else b""
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                if _HAS_AIOHTTP and self._session:
                    async with self._session.post(
                        url, data=encoded, headers=headers,
                    ) as resp:
                        body = await resp.text()
                        try:
                            body_json = json.loads(body)
                        except json.JSONDecodeError:
                            body_json = {}

                        if resp.status == 200:
                            return {"success": True, "body": body_json}
                        else:
                            return {
                                "success": False,
                                "status": resp.status,
                                "error": body[:200],
                            }
                elif _HAS_URLLIB:
                    validated_url = _validate_url(url)

                    def _sync_post() -> Dict[str, Any]:
                        req = urllib.request.Request(
                            validated_url, data=encoded, headers=headers, method="POST",
                        )
                        with urllib.request.urlopen(
                            req, timeout=_HTTP_TIMEOUT,
                        ) as resp:
                            body = resp.read().decode("utf-8")
                            try:
                                body_json = json.loads(body)
                            except json.JSONDecodeError:
                                body_json = {}
                            return {"success": True, "body": body_json}

                    return await asyncio.to_thread(_sync_post)
                else:
                    return None
            except Exception as e:
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "PushChannelProvider: HTTP POST form failed after "
                        "%d attempts: %s",
                        _MAX_RETRIES, e,
                    )
                    return None

        return None

    def _update_rate_limit_from_headers(
        self, headers: Any,
    ) -> None:
        """Update rate limit info from response headers.

        Args:
            headers: HTTP response headers (Mapping or dict-like).
        """
        try:
            remaining = headers.get("X-RateLimit-Remaining")
            if remaining is not None:
                reset_at = headers.get("X-RateLimit-Reset", "0")
                limit = headers.get("X-RateLimit-Limit", "-1")
                self._rate_limit_info = RateLimitInfo(
                    remaining=int(remaining),
                    reset_at=float(reset_at) if reset_at else 0.0,
                    limit=int(limit) if limit else -1,
                )
        except (ValueError, TypeError, AttributeError):
            pass
