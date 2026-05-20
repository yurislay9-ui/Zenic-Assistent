"""
ZENIC-AGENTS — Push Notifications Routing

Internal routing logic for sending push notifications via FCM or Web Push.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from ...._formatter import truncate, sanitize_plain_text
from ...._types import (
    ChannelMessage,
    ChannelResponse,
    DeliveryStatus,
)
from .._utils import _PUSH_PAYLOAD_MAX

logger = logging.getLogger("zenic_agents.channels.push")


async def send_via_fcm(
    provider: Any,
    message: ChannelMessage,
    target: str,
) -> ChannelResponse:
    """Send via FCM based on target format.

    Args:
        provider: PushChannelProvider instance.
        message: Universal message envelope.
        target: FCM target (token, topic:name, condition:expr).
    """
    if not provider._has_fcm:
        return ChannelResponse(
            success=False,
            channel="push",
            status=DeliveryStatus.DRY_RUN,
            error="FCM not configured",
            timestamp=time.time(),
        )

    # Build FCM message
    title = message.title or message.subject or ""
    body = sanitize_plain_text(message.text) if message.text else ""

    fcm_message: Dict[str, Any] = {}

    # Determine target type
    if target.startswith("topic:"):
        fcm_message["topic"] = target[6:]
    elif target.startswith("condition:"):
        fcm_message["condition"] = target[10:]
    else:
        fcm_message["token"] = target

    # Add notification
    notification: Dict[str, str] = {}
    if title:
        notification["title"] = truncate(title, 200)
    if body:
        notification["body"] = truncate(body, 4000)
    if message.image_url:
        notification["image"] = message.image_url
    if notification:
        fcm_message["notification"] = notification

    # Add FCM-specific options
    fcm_options: Dict[str, Any] = {}
    if message.metadata.get("fcm_android"):
        fcm_options["android"] = message.metadata["fcm_android"]
    if message.metadata.get("fcm_apns"):
        fcm_options["apns"] = message.metadata["fcm_apns"]
    if message.metadata.get("fcm_webpush"):
        fcm_options["webpush"] = message.metadata["fcm_webpush"]
    fcm_message.update(fcm_options)

    # Add data payload
    data: Dict[str, str] = {}
    if message.metadata:
        for k, v in message.metadata.items():
            if k.startswith("fcm_"):
                continue  # Skip FCM-specific options already handled
            data[k] = str(v) if not isinstance(v, str) else v
    if message.fields:
        for field in message.fields:
            key = field.get("title", field.get("name", ""))
            val = field.get("value", "")
            if key:
                data[key] = val
    if data:
        fcm_message["data"] = data

    payload = {"message": fcm_message}

    response = await provider._post_fcm(payload)

    with provider._lock:
        if response.success:
            provider._sent_count += 1
            provider._fcm_sent += 1
        else:
            provider._failed_count += 1

    return response


async def send_via_web_push(
    provider: Any,
    message: ChannelMessage,
    user_id: str,
) -> ChannelResponse:
    """Send via Web Push.

    Args:
        provider: PushChannelProvider instance.
        message: Universal message envelope.
        user_id: User identifier with registered subscription.
    """
    if not provider._has_web_push:
        return ChannelResponse(
            success=False,
            channel="push",
            status=DeliveryStatus.DRY_RUN,
            error="Web Push not configured",
            timestamp=time.time(),
        )

    # Look up subscription
    subscription = provider.get_subscription(user_id)
    if not subscription:
        return ChannelResponse(
            success=False,
            channel="push",
            status=DeliveryStatus.FAILED,
            error=f"No Web Push subscription found for user '{user_id}'",
            timestamp=time.time(),
        )

    # Build push payload
    title = message.title or message.subject or ""
    body = sanitize_plain_text(message.text) if message.text else ""

    push_payload: Dict[str, Any] = {
        "title": title,
        "body": body,
    }

    if message.image_url:
        push_payload["icon"] = message.image_url
    if message.metadata:
        push_payload["data"] = {
            k: v for k, v in message.metadata.items()
            if not k.startswith("fcm_")
        }
    if message.fields:
        push_payload["data"] = push_payload.get("data", {})
        push_payload["data"]["fields"] = [
            {k: v for k, v in f.items()} for f in message.fields
        ]

    # Check payload size
    payload_json = json.dumps(push_payload, separators=(",", ":"))
    if len(payload_json) > _PUSH_PAYLOAD_MAX:
        # Truncate body to fit
        max_body = _PUSH_PAYLOAD_MAX - len(json.dumps(
            {k: v for k, v in push_payload.items() if k != "body"},
            separators=(",", ":"),
        )) - 10  # overhead for "body":""
        push_payload["body"] = truncate(body, max_body)
        payload_json = json.dumps(push_payload, separators=(",", ":"))

    response = await provider._post_web_push(subscription, push_payload)

    with provider._lock:
        if response.success:
            provider._sent_count += 1
            provider._webpush_sent += 1
        else:
            provider._failed_count += 1

    return response


async def send_fcm_message(
    provider: Any,
    token: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> ChannelResponse:
    """Send an FCM push notification to a specific device token.

    Args:
        provider: PushChannelProvider instance.
        token: FCM device registration token.
        title: Notification title.
        body: Notification body text.
        data: Optional data payload.
    """
    if not provider._has_fcm:
        return ChannelResponse(
            success=False,
            channel="push",
            status=DeliveryStatus.DRY_RUN,
            error="FCM not configured",
            timestamp=time.time(),
        )

    message_payload: Dict[str, Any] = {"token": token}

    # Add notification
    notification: Dict[str, str] = {}
    if title:
        notification["title"] = title
    if body:
        notification["body"] = body
    if notification:
        message_payload["notification"] = notification

    # Add data
    if data:
        message_payload["data"] = {
            str(k): str(v) if not isinstance(v, str) else v
            for k, v in data.items()
        }

    return await provider._post_fcm({"message": message_payload})


async def send_fcm_to_topic(
    provider: Any,
    topic: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> ChannelResponse:
    """Send an FCM push notification to a topic.

    Args:
        provider: PushChannelProvider instance.
        topic: FCM topic name.
        title: Notification title.
        body: Notification body text.
        data: Optional data payload.
    """
    if not provider._has_fcm:
        return ChannelResponse(
            success=False,
            channel="push",
            status=DeliveryStatus.DRY_RUN,
            error="FCM not configured",
            timestamp=time.time(),
        )

    message_payload: Dict[str, Any] = {"topic": topic}

    notification: Dict[str, str] = {}
    if title:
        notification["title"] = title
    if body:
        notification["body"] = body
    if notification:
        message_payload["notification"] = notification

    if data:
        message_payload["data"] = {
            str(k): str(v) if not isinstance(v, str) else v
            for k, v in data.items()
        }

    return await provider._post_fcm({"message": message_payload})


async def send_web_push_message(
    provider: Any,
    user_id: str,
    payload: Dict[str, Any],
) -> ChannelResponse:
    """Send a Web Push notification to a registered user.

    Args:
        provider: PushChannelProvider instance.
        user_id: User identifier with a registered subscription.
        payload: Push notification payload dict (will be JSON-serialized).
    """
    if not provider._has_web_push:
        return ChannelResponse(
            success=False,
            channel="push",
            status=DeliveryStatus.DRY_RUN,
            error="Web Push not configured",
            timestamp=time.time(),
        )

    subscription = provider.get_subscription(user_id)
    if not subscription:
        return ChannelResponse(
            success=False,
            channel="push",
            status=DeliveryStatus.FAILED,
            error=f"No Web Push subscription found for user '{user_id}'",
            timestamp=time.time(),
        )

    return await provider._post_web_push(subscription, payload)
