"""
ZENIC-AGENTS — Push Notifications Helpers

Dry-run mode helpers and subscription management.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from ...._formatter import sanitize_plain_text
from ...._types import (
    ChannelMessage,
    ChannelResponse,
    ConfirmationRequest,
    DeliveryStatus,
    RateLimitInfo,
)

logger = logging.getLogger("zenic_agents.channels.push")


# ── Dry Run ──────────────────────────────────────────────────────

def dry_run_send(provider: Any, message: ChannelMessage) -> ChannelResponse:
    """Log message without sending (dry-run mode).

    Args:
        provider: PushChannelProvider instance.
        message: Universal message envelope.
    """
    with provider._lock:
        provider._sent_count += 1

    text_preview = sanitize_plain_text(message.text or message.html or "")[:200]
    logger.info(
        "[PUSH DRY-RUN] To: %s | Title: %s | Text: %s",
        message.recipient or "default",
        message.title or message.subject or "(none)",
        text_preview,
    )

    return ChannelResponse(
        success=True,
        channel="push",
        status=DeliveryStatus.DRY_RUN,
        metadata={
            "mode": "dry_run",
            "backend": "none",
            "has_web_push": provider._has_web_push,
            "has_fcm": provider._has_fcm,
        },
        timestamp=time.time(),
    )


def dry_run_confirmation(
    provider: Any,
    request: ConfirmationRequest,
) -> ChannelResponse:
    """Log confirmation without sending (dry-run mode).

    Args:
        provider: PushChannelProvider instance.
        request: Confirmation request with options.
    """
    with provider._lock:
        provider._confirmation_count += 1

    logger.info(
        "[PUSH DRY-RUN] Confirmation: %s | Options: %s | Recipient: %s",
        request.title,
        list(request.options),
        request.recipient or "default",
    )

    return ChannelResponse(
        success=True,
        channel="push",
        status=DeliveryStatus.DRY_RUN,
        metadata={
            "mode": "dry_run",
            "action_id": request.action_id,
        },
        timestamp=time.time(),
    )


# ── Subscription Management ──────────────────────────────────────

def register_subscription(
    provider: Any,
    user_id: str,
    subscription: Dict[str, Any],
) -> None:
    """Register a Web Push subscription for a user.

    Args:
        provider: PushChannelProvider instance.
        user_id: Unique identifier for the user.
        subscription: PushSubscription JSON object with keys:
                      - endpoint: Push server URL
                      - keys.p256dh: ECDH public key (base64url)
                      - keys.auth: Authentication secret (base64url)
    """
    with provider._sub_lock:
        provider._subscriptions[user_id] = subscription

    logger.debug(
        "PushChannelProvider: registered subscription for user '%s' "
        "(endpoint=%s)",
        user_id,
        subscription.get("endpoint", "N/A")[:60],
    )


def unregister_subscription(provider: Any, user_id: str) -> bool:
    """Remove a Web Push subscription.

    Args:
        provider: PushChannelProvider instance.
        user_id: User identifier to remove.

    Returns:
        True if a subscription was removed, False if not found.
    """
    with provider._sub_lock:
        removed = user_id in provider._subscriptions
        provider._subscriptions.pop(user_id, None)

    if removed:
        logger.debug(
            "PushChannelProvider: unregistered subscription for user '%s'",
            user_id,
        )
    return removed


def get_subscription(
    provider: Any,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    """Get a Web Push subscription for a user.

    Args:
        provider: PushChannelProvider instance.
        user_id: User identifier.

    Returns:
        Subscription dict or None if not found.
    """
    with provider._sub_lock:
        return provider._subscriptions.get(user_id)
