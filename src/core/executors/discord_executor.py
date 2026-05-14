"""
ZENIC-AGENTS - DiscordExecutor (Phase 3)

9th executor for sending messages to Discord channels via webhooks.
Supports rich embeds, rate limiting, and thread creation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from .base import ActionExecutor, ActionResult, _validate_url, _HAS_AIOHTTP

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  DISCORD WEBHOOK LIMITS
# ──────────────────────────────────────────────────────────────

MAX_EMBED_FIELDS = 25
MAX_EMBED_TITLE = 256
MAX_EMBED_DESCRIPTION = 4096
MAX_EMBED_FIELD_NAME = 256
MAX_EMBED_FIELD_VALUE = 1024
MAX_CONTENT_LENGTH = 2000
MAX_USERNAME_LENGTH = 80


class DiscordExecutor(ActionExecutor):
    """Ejecutor de mensajes Discord via Webhook.

    Features:
      - Plain text and rich embed messages
      - Multiple embeds per message
      - Thread creation for forum channels
      - Rate limiting (Discord rate limit headers respected)
      - Automatic retry with exponential backoff
      - Username/avatar override support
      - Fallback to log when Discord not configured

    Config: {
        webhook_url, content, username, avatar_url,
        embeds, thread_name, dry_run
    }
    """

    def __init__(self) -> None:
        self._rate_limit_remaining: int = 5
        self._rate_limit_reset: float = 0.0
        self._last_send_time: float = 0.0

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        webhook_url = config.get("webhook_url", os.environ.get("DISCORD_WEBHOOK_URL", ""))
        content = config.get("content", "")
        username = config.get("username", "")
        avatar_url = config.get("avatar_url", "")
        embeds = config.get("embeds", [])
        thread_name = config.get("thread_name", "")
        dry_run = config.get("dry_run", False)

        # Validate webhook URL
        if not webhook_url or dry_run:
            return await self._dry_run(content, embeds, start)

        if not _validate_url(webhook_url):
            return ActionResult(
                False, {"webhook_url": webhook_url},
                "Invalid Discord webhook URL", self._elapsed_ms(start)
            )

        # Build payload
        payload = self._build_payload(content, username, avatar_url, embeds, thread_name)

        # Validate payload
        validation_errors = self._validate_payload(payload)
        if validation_errors:
            return ActionResult(
                False, {"errors": validation_errors},
                f"Discord payload validation failed: {validation_errors}",
                self._elapsed_ms(start)
            )

        # Send with retry
        result = await self._send_with_retry(webhook_url, payload)
        elapsed = self._elapsed_ms(start)

        if result.get("success"):
            logger.info("DiscordExecutor: Message sent successfully")
            return ActionResult(True, {
                "channel": "discord",
                "content_length": len(content),
                "embeds_count": len(embeds),
                "has_thread": bool(thread_name),
            }, duration_ms=elapsed)

        return ActionResult(
            False, {"channel": "discord"},
            result.get("error", "Discord send failed"), elapsed
        )

    def _build_payload(
        self,
        content: str,
        username: str,
        avatar_url: str,
        embeds: List[Dict[str, Any]],
        thread_name: str,
    ) -> Dict[str, Any]:
        """Build Discord webhook payload."""
        payload: Dict[str, Any] = {}

        if content:
            payload["content"] = content[:MAX_CONTENT_LENGTH]

        if username:
            payload["username"] = username[:MAX_USERNAME_LENGTH]

        if avatar_url:
            payload["avatar_url"] = avatar_url

        if embeds:
            payload["embeds"] = self._sanitize_embeds(embeds)

        if thread_name:
            payload["thread_name"] = thread_name

        return payload

    def _sanitize_embeds(self, embeds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sanitize and truncate embed fields to Discord limits."""
        sanitized = []
        for embed in embeds[:10]:  # Max 10 embeds per message
            s_embed: Dict[str, Any] = {}

            if "title" in embed:
                s_embed["title"] = str(embed["title"])[:MAX_EMBED_TITLE]
            if "description" in embed:
                s_embed["description"] = str(embed["description"])[:MAX_EMBED_DESCRIPTION]
            if "color" in embed:
                s_embed["color"] = int(embed["color"]) & 0xFFFFFF
            if "url" in embed:
                s_embed["url"] = str(embed["url"])

            # Fields
            if "fields" in embed:
                fields = []
                for f in embed["fields"][:MAX_EMBED_FIELDS]:
                    fields.append({
                        "name": str(f.get("name", ""))[:MAX_EMBED_FIELD_NAME],
                        "value": str(f.get("value", ""))[:MAX_EMBED_FIELD_VALUE],
                        "inline": bool(f.get("inline", False)),
                    })
                s_embed["fields"] = fields

            # Footer
            if "footer" in embed:
                s_embed["footer"] = {"text": str(embed["footer"].get("text", ""))[:2048]}

            # Timestamp
            if "timestamp" in embed:
                s_embed["timestamp"] = str(embed["timestamp"])

            sanitized.append(s_embed)

        return sanitized

    def _validate_payload(self, payload: Dict[str, Any]) -> List[str]:
        """Validate payload against Discord limits."""
        errors: List[str] = []

        if not payload.get("content") and not payload.get("embeds"):
            errors.append("Payload must have content or embeds")

        content = payload.get("content", "")
        if len(content) > MAX_CONTENT_LENGTH:
            errors.append(f"Content exceeds {MAX_CONTENT_LENGTH} characters")

        embeds = payload.get("embeds", [])
        if len(embeds) > 10:
            errors.append("Maximum 10 embeds per message")

        return errors

    async def _send_with_retry(self, url: str, payload: Dict[str, Any], max_retries: int = 3) -> Dict[str, Any]:
        """Send Discord webhook with retry and rate limit handling."""
        # Wait for rate limit if needed
        if self._rate_limit_remaining <= 0:
            wait_time = max(0, self._rate_limit_reset - time.time()) + 0.5
            if wait_time > 0:
                logger.info("DiscordExecutor: Rate limited, waiting %.1fs", wait_time)
                await asyncio.sleep(wait_time)

        for attempt in range(max_retries):
            try:
                if _HAS_AIOHTTP:
                    return await self._send_aiohttp(url, payload)
                else:
                    return await asyncio.to_thread(self._send_urllib, url, payload)
            except Exception as e:
                wait = (2 ** attempt) * 0.5
                logger.warning(
                    "DiscordExecutor: Attempt %d/%d failed: %s. Retry in %.1fs",
                    attempt + 1, max_retries, e, wait,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait)

        return {"success": False, "error": "All retry attempts failed"}

    async def _send_aiohttp(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send via aiohttp."""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                self._update_rate_limits(resp.headers)
                if resp.status == 204 or resp.status == 200:
                    return {"success": True, "status": resp.status}
                body = await resp.text()
                return {"success": False, "error": f"HTTP {resp.status}: {body[:200]}"}

    def _send_urllib(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send via urllib (fallback)."""
        import urllib.request
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 204):
                return {"success": True, "status": resp.status}
            return {"success": False, "error": f"HTTP {resp.status}"}

    def _update_rate_limits(self, headers: Any) -> None:
        """Update rate limit tracking from Discord response headers."""
        try:
            if hasattr(headers, 'get'):
                remaining = headers.get("X-RateLimit-Remaining", "")
                reset = headers.get("X-RateLimit-Reset", "")
                if remaining:
                    self._rate_limit_remaining = int(remaining)
                if reset:
                    self._rate_limit_reset = float(reset)
        except (ValueError, TypeError):
            pass

    async def _dry_run(self, content: str, embeds: List, start: float) -> ActionResult:
        """Dry-run mode: log message without sending."""
        elapsed = self._elapsed_ms(start)
        logger.info("DiscordExecutor [DRY-RUN]: content=%s embeds=%d", content[:100], len(embeds))
        return ActionResult(True, {
            "mode": "dry_run",
            "channel": "discord",
            "content_length": len(content),
            "embeds_count": len(embeds),
        }, duration_ms=elapsed)
