"""graph_api — Transport layer (send_with_retry, send_once, dry_run)."""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from typing import Any, Dict, List, Optional

from ._types import *  # noqa: F403
from ._helpers import _send_with_retry, _send_once, _dry_run_response, _upload_attachment_session


class GraphAPITransportMixin:
    """Transport methods for GraphAPIEmailProvider."""

    # ── Private: Sending ──────────────────────────────────────

    async def _send_with_retry(
        self,
        payload: Dict[str, Any],
        sender: str,
    ) -> Dict[str, Any]:
        """Send email with exponential backoff retry."""
        last_error = ""
        for attempt in range(_MAX_RETRIES):  # noqa: F821
            try:
                result = await self._send_once(payload, sender)
                if result.get("success"):
                    self._send_count += 1
                    return result

                # Check if retryable
                status_code = result.get("status_code", 0)
                if status_code == 429:
                    # Rate limited — respect Retry-After header
                    retry_after = result.get("retry_after_seconds", 60)
                    __import__("logging").getLogger("zenic_agents.executors.graph_api").warning(
                        "GraphAPIEmailProvider: Rate limited (429), retrying after %.1fs",
                        retry_after,
                    )
                    await asyncio.sleep(retry_after)
                    continue

                if status_code in (401, 403):
                    # Auth error — don't retry
                    self._error_count += 1
                    return result

                if status_code >= 500:
                    # Server error — retry with backoff
                    backoff = _INITIAL_BACKOFF_SECONDS * (_BACKOFF_MULTIPLIER ** attempt)  # noqa: F821
                    __import__("logging").getLogger("zenic_agents.executors.graph_api").warning(
                        "GraphAPIEmailProvider: Server error (%d), retrying in %.1fs "
                        "(attempt %d/%d)",
                        status_code, backoff, attempt + 1, _MAX_RETRIES,  # noqa: F821
                    )
                    await asyncio.sleep(backoff)
                    last_error = result.get("error", f"HTTP {status_code}")
                    continue

                # Non-retryable error
                self._error_count += 1
                return result

            except asyncio.TimeoutError:
                backoff = _INITIAL_BACKOFF_SECONDS * (_BACKOFF_MULTIPLIER ** attempt)  # noqa: F821
                __import__("logging").getLogger("zenic_agents.executors.graph_api").warning(
                    "GraphAPIEmailProvider: Request timed out, retrying in %.1fs "
                    "(attempt %d/%d)",
                    backoff, attempt + 1, _MAX_RETRIES,  # noqa: F821
                )
                last_error = "Request timed out"
                await asyncio.sleep(backoff)

            except Exception as exc:
                backoff = _INITIAL_BACKOFF_SECONDS * (_BACKOFF_MULTIPLIER ** attempt)  # noqa: F821
                __import__("logging").getLogger("zenic_agents.executors.graph_api").warning(
                    "GraphAPIEmailProvider: Unexpected error: %s, retrying in %.1fs "
                    "(attempt %d/%d)",
                    exc, backoff, attempt + 1, _MAX_RETRIES,  # noqa: F821
                )
                last_error = str(exc)
                await asyncio.sleep(backoff)

        # All retries exhausted
        self._error_count += 1
        return {
            "success": False,
            "message_id": "",
            "status_code": 0,
            "error": f"All {_MAX_RETRIES} retries exhausted: {last_error}",  # noqa: F821
        }

    async def _send_once(
        self,
        payload: Dict[str, Any],
        sender: str,
    ) -> Dict[str, Any]:
        """Make a single send attempt via Graph API."""
        async with self._lock:
            token = await self._token_manager.get_token(self._service_name)

        if not token.access_token or token.is_expired:
            return {
                "success": False,
                "message_id": "",
                "status_code": 401,
                "error": "No valid access token available",
            }

        # Determine endpoint
        if sender:
            endpoint = f"{_GRAPH_BASE_URL}/users/{sender}/sendMail"  # noqa: F821
        else:
            endpoint = f"{_GRAPH_BASE_URL}/me/sendMail"  # noqa: F821

        try:
            async with aiohttp.ClientSession() as session:  # noqa: F821
                headers = {
                    "Authorization": token.authorization_header,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }

                async with session.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),  # noqa: F821
                ) as response:
                    # Update rate limit from headers
                    resp_headers = {
                        k: v for k, v in response.headers.items()
                    }
                    self._rate_limit.update_from_headers(resp_headers)

                    if response.status == 202:
                        message_id = response.headers.get(
                            "Location", f"msg-{uuid.uuid4().hex[:12]}"
                        )
                        return {
                            "success": True,
                            "message_id": message_id,
                            "status_code": response.status,
                        }

                    # Error response
                    try:
                        error_body = await response.json()
                        error_msg = (
                            error_body.get("error", {}).get("message", "")
                            or f"HTTP {response.status}"
                        )
                    except Exception:
                        error_msg = f"HTTP {response.status}"

                    result: Dict[str, Any] = {
                        "success": False,
                        "message_id": "",
                        "status_code": response.status,
                        "error": error_msg,
                    }

                    # Handle 429 rate limit
                    if response.status == 429:
                        retry_after = response.headers.get("Retry-After", "60")
                        try:
                            result["retry_after_seconds"] = float(retry_after)
                        except (ValueError, TypeError):
                            result["retry_after_seconds"] = 60.0

                    return result

        except asyncio.TimeoutError:
            raise
        except Exception as exc:
            return {
                "success": False,
                "message_id": "",
                "status_code": 0,
                "error": f"Request failed: {exc}",
            }
