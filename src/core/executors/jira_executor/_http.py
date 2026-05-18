"""ZENIC-AGENTS - Jira Executor: HTTP Mixin"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from ..base import _HAS_AIOHTTP, _validate_url_ssrf

logger = logging.getLogger(__name__)

try:
    import urllib.request
    import urllib.error
    _HAS_URLLIB = True
except ImportError:
    _HAS_URLLIB = False

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.5
_HTTP_TIMEOUT = 30


class _HttpMixin:
    """Mixin for Jira HTTP request methods."""

    async def _jira_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute an HTTP request against the Jira REST API.

        Uses aiohttp when available, falls back to urllib.
        Implements exponential backoff retry (up to _MAX_RETRIES).

        Returns:
            Dict with keys: status, body, headers.
        """
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                if _HAS_AIOHTTP:
                    return await self._jira_request_aiohttp(
                        method, url, headers, json_data, params,
                    )
                elif _HAS_URLLIB:
                    return await self._jira_request_urllib(
                        method, url, headers, json_data, params,
                    )
                else:
                    return {
                        "status": 0,
                        "body": {"errorMessages": ["No HTTP library available"]},
                        "headers": {},
                    }
            except Exception as exc:
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "JiraExecutor: attempt %d/%d failed for %s %s: %s",
                        attempt, _MAX_RETRIES, method, url, exc,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "JiraExecutor: all %d attempts failed for %s %s: %s",
                        _MAX_RETRIES, method, url, exc,
                    )
                    return {
                        "status": 0,
                        "body": {
                            "errorMessages": [
                                f"HTTP error after {_MAX_RETRIES} attempts: {exc}"
                            ],
                        },
                        "headers": {},
                    }

        # Should not be reached, but defensive
        return {
            "status": 0,
            "body": {"errorMessages": ["Unexpected retry loop exit"]},
            "headers": {},
        }

    async def _jira_request_aiohttp(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        json_data: Optional[Dict[str, Any]],
        params: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Execute request via aiohttp."""
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method,
                url,
                headers=headers,
                json=json_data,
                params=params,
            ) as resp:
                # Track rate limits from response headers
                remaining = resp.headers.get("X-RateLimit-Remaining")
                if remaining is not None:
                    with self._lock:
                        self._rate_limit_remaining = int(remaining)
                        reset_val = resp.headers.get("X-RateLimit-Reset", "0")
                        try:
                            self._rate_limit_reset_at = float(reset_val)
                        except (ValueError, TypeError):
                            self._rate_limit_reset_at = None

                # Handle 429 rate limiting
                if resp.status == 429:
                    retry_after = float(resp.headers.get("Retry-After", "5"))
                    logger.warning(
                        "JiraExecutor: rate limited, retry after %.1fs",
                        retry_after,
                    )
                    await asyncio.sleep(retry_after)
                    # Raise to trigger retry
                    raise RuntimeError(f"Rate limited, retry after {retry_after}s")

                body = await resp.json()
                return {
                    "status": resp.status,
                    "body": body,
                    "headers": dict(resp.headers),
                }

    async def _jira_request_urllib(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        json_data: Optional[Dict[str, Any]],
        params: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Execute request via urllib (sync, wrapped in asyncio.to_thread)."""

        # Append query params to URL
        if params:
            filtered = {k: v for k, v in params.items() if v is not None}
            if filtered:
                from urllib.parse import urlencode
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}{urlencode(filtered)}"

        validated_url = _validate_url_ssrf(url)

        def _sync_request() -> Dict[str, Any]:
            data = (
                json.dumps(json_data).encode("utf-8") if json_data else None
            )
            req = urllib.request.Request(
                validated_url,
                data=data,
                headers=headers,
                method=method.upper(),
            )
            try:
                with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                    body_text = resp.read().decode("utf-8")
                    body = json.loads(body_text) if body_text else {}
                    return {
                        "status": resp.status,
                        "body": body,
                        "headers": dict(resp.headers),
                    }
            except urllib.error.HTTPError as exc:
                body_text = ""
                try:
                    body_text = exc.read().decode("utf-8")[:2000]
                except Exception:
                    pass
                body: Dict[str, Any] = {}
                try:
                    body = json.loads(body_text) if body_text else {}
                except json.JSONDecodeError:
                    body = {"errorMessages": [body_text]}

                if exc.code == 429:
                    retry_after = float(exc.headers.get("Retry-After", "5"))
                    raise RuntimeError(
                        f"Rate limited, retry after {retry_after}s"
                    )

                return {
                    "status": exc.code,
                    "body": body,
                    "headers": dict(exc.headers),
                }
            except Exception as exc:
                return {
                    "status": 0,
                    "body": {"errorMessages": [str(exc)]},
                    "headers": {},
                }

        return await asyncio.to_thread(_sync_request)

    # ── Operation: create_issue ────────────────────────────────
