"""
ZENIC-AGENTS — Microsoft Graph API HTTP Client (Phase 2)

Low-level HTTP operations: single send, retry logic, and
large attachment upload sessions.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional

from ..oauth2 import OAuth2TokenManager
from ._types import (
    _HAS_AIOHTTP,
    _GRAPH_BASE_URL,
    _MAX_RETRIES,
    _INITIAL_BACKOFF_SECONDS,
    _BACKOFF_MULTIPLIER,
    _RateLimitState,
)

if _HAS_AIOHTTP:
    import aiohttp

logger = logging.getLogger("zenic_agents.email_parts.graph_api")


async def send_once(
    provider: Any,
    payload: Dict[str, Any],
    sender: str,
    service_name: str,
    token_manager: OAuth2TokenManager,
    rate_limit: _RateLimitState,
) -> Dict[str, Any]:
    """Make a single send attempt via Graph API.

    Args:
        provider: GraphAPIEmailProvider instance (for lock access).
        payload: The sendMail request payload.
        sender: Sender email address.
        service_name: Service name in the token manager.
        token_manager: OAuth2TokenManager instance.
        rate_limit: Rate limit state tracker.

    Returns:
        Dict with success, message_id, status_code, error, etc.
    """
    async with provider._lock:
        token = await token_manager.get_token(service_name)

    if not token.access_token or token.is_expired:
        return {
            "success": False,
            "message_id": "",
            "status_code": 401,
            "error": "No valid access token available",
        }

    # Determine endpoint
    # If sender specified, use /users/{sender}/sendMail
    # Otherwise, use /me/sendMail
    if sender:
        endpoint = f"{_GRAPH_BASE_URL}/users/{sender}/sendMail"
    else:
        endpoint = f"{_GRAPH_BASE_URL}/me/sendMail"

    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": token.authorization_header,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            async with session.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                # Update rate limit from headers
                resp_headers = {
                    k: v for k, v in response.headers.items()
                }
                rate_limit.update_from_headers(resp_headers)

                if response.status == 202:
                    # Success — Graph API returns 202 Accepted
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


async def send_with_retry(
    provider: Any,
    payload: Dict[str, Any],
    sender: str,
    service_name: str,
    token_manager: OAuth2TokenManager,
    rate_limit: _RateLimitState,
    send_count_ref: list,
    error_count_ref: list,
) -> Dict[str, Any]:
    """Send email with exponential backoff retry.

    Args:
        provider: GraphAPIEmailProvider instance.
        payload: The sendMail request payload.
        sender: Sender email address.
        service_name: Service name in the token manager.
        token_manager: OAuth2TokenManager instance.
        rate_limit: Rate limit state tracker.
        send_count_ref: Mutable [count] for successful sends.
        error_count_ref: Mutable [count] for errors.

    Returns:
        Dict with success, message_id, status_code, error, etc.
    """
    last_error = ""
    for attempt in range(_MAX_RETRIES):
        try:
            result = await send_once(
                provider, payload, sender, service_name,
                token_manager, rate_limit,
            )
            if result.get("success"):
                send_count_ref[0] += 1
                return result

            # Check if retryable
            status_code = result.get("status_code", 0)
            if status_code == 429:
                # Rate limited — respect Retry-After header
                retry_after = result.get("retry_after_seconds", 60)
                logger.warning(
                    "GraphAPIEmailProvider: Rate limited (429), retrying after %.1fs",
                    retry_after,
                )
                await asyncio.sleep(retry_after)
                continue

            if status_code in (401, 403):
                # Auth error — don't retry
                error_count_ref[0] += 1
                return result

            if status_code >= 500:
                # Server error — retry with backoff
                backoff = _INITIAL_BACKOFF_SECONDS * (_BACKOFF_MULTIPLIER ** attempt)
                logger.warning(
                    "GraphAPIEmailProvider: Server error (%d), retrying in %.1fs "
                    "(attempt %d/%d)",
                    status_code, backoff, attempt + 1, _MAX_RETRIES,
                )
                await asyncio.sleep(backoff)
                last_error = result.get("error", f"HTTP {status_code}")
                continue

            # Non-retryable error
            error_count_ref[0] += 1
            return result

        except asyncio.TimeoutError:
            backoff = _INITIAL_BACKOFF_SECONDS * (_BACKOFF_MULTIPLIER ** attempt)
            logger.warning(
                "GraphAPIEmailProvider: Request timed out, retrying in %.1fs "
                "(attempt %d/%d)",
                backoff, attempt + 1, _MAX_RETRIES,
            )
            last_error = "Request timed out"
            await asyncio.sleep(backoff)

        except Exception as exc:
            backoff = _INITIAL_BACKOFF_SECONDS * (_BACKOFF_MULTIPLIER ** attempt)
            logger.warning(
                "GraphAPIEmailProvider: Unexpected error: %s, retrying in %.1fs "
                "(attempt %d/%d)",
                exc, backoff, attempt + 1, _MAX_RETRIES,
            )
            last_error = str(exc)
            await asyncio.sleep(backoff)

    # All retries exhausted
    error_count_ref[0] += 1
    return {
        "success": False,
        "message_id": "",
        "status_code": 0,
        "error": f"All {_MAX_RETRIES} retries exhausted: {last_error}",
    }


async def upload_attachment_session(
    provider: Any,
    sender: str,
    attachment: Dict[str, Any],
    service_name: str,
    token_manager: OAuth2TokenManager,
) -> Optional[str]:
    """Upload a large attachment using a Graph API upload session.

    For attachments larger than 4MB, creates an upload session
    and uploads the file in chunks.

    Args:
        provider: GraphAPIEmailProvider instance.
        sender: Sender email for endpoint construction.
        attachment: Attachment dict with name, content_bytes, size, content_type.
        service_name: Service name in the token manager.
        token_manager: OAuth2TokenManager instance.

    Returns:
        Attachment ID if successful, None otherwise.
    """
    file_name = attachment.get("name", "attachment")
    file_size = attachment.get("size", 0)
    content_type = attachment.get("content_type", "application/octet-stream")

    if sender:
        endpoint = f"{_GRAPH_BASE_URL}/users/{sender}/messages/attachments/createUploadSession"
    else:
        endpoint = f"{_GRAPH_BASE_URL}/me/messages/attachments/createUploadSession"

    try:
        async with provider._lock:
            token = await token_manager.get_token(service_name)

        if not token.access_token or token.is_expired:
            logger.warning("GraphAPIEmailProvider: Cannot upload attachment — no valid token")
            return None

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": token.authorization_header,
                "Content-Type": "application/json",
            }

            # Create upload session
            upload_body = {
                "AttachmentItem": {
                    "attachmentType": "file",
                    "name": file_name,
                    "size": file_size,
                    "contentType": content_type,
                }
            }

            async with session.post(
                endpoint,
                json=upload_body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status not in (200, 201):
                    error_body = await response.json()
                    logger.warning(
                        "GraphAPIEmailProvider: Failed to create upload session: %s",
                        error_body.get("error", {}).get("message", response.status),
                    )
                    return None

                session_data = await response.json()
                upload_url = session_data.get("uploadUrl", "")

            if not upload_url:
                logger.warning("GraphAPIEmailProvider: No upload URL in session response")
                return None

            # Upload file in chunks (4 MB chunks)
            content_bytes = attachment.get("content_bytes", b"")
            chunk_size = 4 * 1024 * 1024
            offset = 0

            while offset < len(content_bytes):
                chunk = content_bytes[offset:offset + chunk_size]
                chunk_len = len(chunk)
                content_range = f"bytes {offset}-{offset + chunk_len - 1}/{file_size}"

                async with session.put(
                    upload_url,
                    data=chunk,
                    headers={
                        "Content-Length": str(chunk_len),
                        "Content-Range": content_range,
                    },
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as put_response:
                    if put_response.status not in (200, 201, 202):
                        logger.warning(
                            "GraphAPIEmailProvider: Chunk upload failed at offset %d: HTTP %d",
                            offset, put_response.status,
                        )
                        return None

                    if put_response.status in (200, 201):
                        # Upload complete
                        result = await put_response.json()
                        return result.get("id", "uploaded")

                offset += chunk_len

            return "uploaded"

    except Exception as exc:
        logger.warning(
            "GraphAPIEmailProvider: Attachment upload session failed: %s", exc,
        )
        return None
