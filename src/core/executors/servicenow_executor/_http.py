"""ZENIC-AGENTS - ServiceNow Executor: HTTP Mixin"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from ..base import _HAS_AIOHTTP, _validate_url_ssrf

logger = logging.getLogger(__name__)

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.5


class _HttpMixin:
    """Mixin for ServiceNow HTTP request methods."""

    async def _snow_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute an HTTP request against the ServiceNow API with retry.

        Uses aiohttp when available; falls back to urllib otherwise.

        Args:
            method: HTTP method (GET, POST, PATCH, PUT, DELETE).
            url: Full API URL.
            headers: Request headers (including auth).
            json_data: Optional JSON body.

        Returns:
            Dict with ``status``, ``body``, ``headers`` keys.
            On failure, includes ``error`` key.
        """
        with self._lock:
            self._stats["requests_total"] += 1

        last_error: Optional[str] = None

        for attempt in range(_MAX_RETRIES):
            try:
                if _AIOHTTP_AVAILABLE:
                    result = await self._snow_request_aiohttp(
                        method, url, headers, json_data,
                    )
                else:
                    result = await self._snow_request_urllib(
                        method, url, headers, json_data,
                    )

                # ── Track rate limits from response ───────────
                resp_headers = result.get("headers", {})
                remaining = resp_headers.get("X-RateLimit-Remaining") or resp_headers.get("x-ratelimit-remaining")
                if remaining is not None:
                    try:
                        self._update_rate_limit(url, int(remaining))
                    except (ValueError, TypeError):
                        pass

                # ── Success ───────────────────────────────────
                with self._lock:
                    self._stats["requests_success"] += 1

                return result

            except Exception as exc:
                last_error = str(exc)
                with self._lock:
                    self._stats["retries_total"] += 1

                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "ServiceNowExecutor: request failed (attempt %d/%d), "
                        "retrying in %.1fs — %s",
                        attempt + 1, _MAX_RETRIES, delay, exc,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "ServiceNowExecutor: request failed after %d attempts — %s",
                        _MAX_RETRIES, exc,
                    )

        with self._lock:
            self._stats["requests_failed"] += 1

        return {
            "status": 0,
            "body": {},
            "headers": {},
            "error": last_error or "Max retries exceeded",
        }

    async def _snow_request_aiohttp(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute request using aiohttp (async-native)."""
        import aiohttp  # type: ignore[import-untyped]

        async with aiohttp.ClientSession() as session:
            kwargs: Dict[str, Any] = {
                "headers": headers,
                "timeout": aiohttp.ClientTimeout(total=30),
            }
            if json_data is not None:
                kwargs["json"] = json_data

            async with session.request(method, url, **kwargs) as resp:
                body = await resp.text()
                resp_headers = dict(resp.headers)

                try:
                    parsed_body = json.loads(body) if body else {}
                except json.JSONDecodeError:
                    parsed_body = {"raw": body}

                return {
                    "status": resp.status,
                    "body": parsed_body,
                    "headers": resp_headers,
                }

    async def _snow_request_urllib(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute request using urllib (sync, wrapped in to_thread)."""

        validated_url = _validate_url_ssrf(url)

        def _do() -> Dict[str, Any]:
            data = None
            if json_data is not None:
                data = json.dumps(json_data).encode("utf-8")

            req = urllib.request.Request(validated_url, data=data, headers=headers, method=method)

            try:
                with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                    body_text = resp.read().decode("utf-8")
                    resp_headers = dict(resp.headers)

                    try:
                        parsed = json.loads(body_text) if body_text else {}
                    except json.JSONDecodeError:
                        parsed = {"raw": body_text}

                    return {
                        "status": resp.status,
                        "body": parsed,
                        "headers": resp_headers,
                    }
            except urllib.error.HTTPError as exc:
                body_text = ""
                try:
                    body_text = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    pass

                try:
                    parsed = json.loads(body_text) if body_text else {}
                except json.JSONDecodeError:
                    parsed = {"raw": body_text} if body_text else {}

                return {
                    "status": exc.code,
                    "body": parsed,
                    "headers": dict(exc.headers) if exc.headers else {},
                    "error": str(exc),
                }

        return await asyncio.to_thread(_do)

    # ──────────────────────────────────────────────────────────
    #  RATE-LIMIT TRACKING
    # ──────────────────────────────────────────────────────────

    def _update_rate_limit(self, url: str, remaining: int) -> None:
        """Update per-instance rate-limit counter from response headers."""
        # Extract instance hostname for per-instance tracking
        parsed = urllib.parse.urlparse(url)
        instance_key = parsed.netloc

        with self._lock:
            self._rate_limits[instance_key] = {
                "remaining": remaining,
                "updated_at": time.time(),
            }

        if remaining < 10:
            logger.warning(
                "ServiceNowExecutor: rate limit low for %s — %d remaining",
                instance_key, remaining,
            )

    # ──────────────────────────────────────────────────────────
    #  OPERATION IMPLEMENTATIONS
    # ──────────────────────────────────────────────────────────
