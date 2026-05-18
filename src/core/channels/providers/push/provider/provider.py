"""
ZENIC-AGENTS — Push Notifications Channel Provider (Thin Class)

Outbound: Web Push (VAPID) and Firebase Cloud Messaging (FCM HTTP v1)

This module contains the thin PushChannelProvider class that delegates
routing and helper logic to _routing and _helpers sub-modules.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, FrozenSet, List, Optional
from typing import Set

from ...._formatter import MessageFormatter, truncate, sanitize_plain_text
from ...._protocol import ChannelProvider
from ...._types import (
    ChannelCapability,
    ChannelMessage,
    ChannelResponse,
    ConfirmationRequest,
    DeliveryStatus,
    RateLimitInfo,
)
from .._vapid import _VapidMixin
from .._fcm_auth import _FcmAuthMixin
from .._fcm_http import _FcmHttpMixin
from .._webpush_http import _WebPushHttpMixin
from .._utils import (
    _HAS_AIOHTTP,
    _HAS_CRYPTOGRAPHY,
    _PUSH_PAYLOAD_MAX,
)
from ._routing import (
    send_via_fcm,
    send_via_web_push,
    send_fcm_message,
    send_fcm_to_topic,
    send_web_push_message,
)
from ._helpers import (
    dry_run_send,
    dry_run_confirmation,
    register_subscription,
    unregister_subscription,
    get_subscription,
)

logger = logging.getLogger("zenic_agents.channels.push")


class PushChannelProvider(_VapidMixin, _FcmAuthMixin, _FcmHttpMixin, _WebPushHttpMixin):
    """Push Notifications channel provider.

    Supports two backends:
      1. Web Push API (VAPID) — browser push notifications
      2. Firebase Cloud Messaging (FCM) — mobile push notifications

    Routing is based on recipient format:
      - 'fcm:<token>'           -> FCM to a specific device token
      - 'fcm:topic:<name>'     -> FCM to a topic
      - 'fcm:condition:<expr>' -> FCM to a condition
      - 'webpush:<user_id>'    -> Web Push to a registered subscription
      - Otherwise              -> try both if configured

    Dry-run mode when no backends are configured.
    """

    def __init__(
        self,
        vapid_private_key: Optional[str] = None,
        vapid_public_key: Optional[str] = None,
        vapid_subject: Optional[str] = None,
        fcm_project_id: Optional[str] = None,
        fcm_service_account_key_path: Optional[str] = None,
    ) -> None:
        # Web Push (VAPID) configuration
        self._vapid_private_key = vapid_private_key or os.environ.get("VAPID_PRIVATE_KEY", "")
        self._vapid_public_key = vapid_public_key or os.environ.get("VAPID_PUBLIC_KEY", "")
        self._vapid_subject = vapid_subject or os.environ.get("VAPID_SUBJECT", "")

        # FCM configuration
        self._fcm_project_id = fcm_project_id or os.environ.get("FCM_PROJECT_ID", "")
        self._fcm_service_account_key_path = (
            fcm_service_account_key_path
            or os.environ.get("FCM_SERVICE_ACCOUNT_KEY", "")
        )

        # Loaded FCM service account data (lazy)
        self._fcm_service_account_data: Optional[Dict[str, str]] = None
        self._fcm_access_token: str = ""
        self._fcm_token_expiry: float = 0.0

        # Web Push subscription storage (user_id -> subscription JSON)
        self._subscriptions: Dict[str, Dict[str, Any]] = {}
        self._sub_lock = threading.Lock()

        # VAPID private key object (lazy)
        self._vapid_private_key_obj: Optional[Any] = None

        # Stats
        self._lock = threading.Lock()
        self._sent_count: int = 0
        self._failed_count: int = 0
        self._confirmation_count: int = 0
        self._webpush_sent: int = 0
        self._fcm_sent: int = 0
        self._started: bool = False
        self._rate_limit_info = RateLimitInfo()

        # HTTP session
        self._session: Optional[Any] = None  # aiohttp.ClientSession

    # ── ChannelProvider Protocol ────────────────────────────────

    @property
    def name(self) -> str:
        return "push"

    @property
    def capabilities(self) -> FrozenSet[ChannelCapability]:
        return frozenset({
            ChannelCapability.SEND_TEXT,
            ChannelCapability.SEND_RICH,
            ChannelCapability.SEND_PUSH,
            ChannelCapability.SEND_CONFIRMATION,
        })

    @property
    def is_available(self) -> bool:
        """Available if at least one backend is configured."""
        return self._has_web_push or self._has_fcm

    @property
    def _has_web_push(self) -> bool:
        """Whether Web Push (VAPID) is fully configured."""
        return bool(
            self._vapid_private_key
            and self._vapid_public_key
            and self._vapid_subject
        )

    @property
    def _has_fcm(self) -> bool:
        """Whether FCM is fully configured."""
        return bool(self._fcm_project_id and self._fcm_service_account_key_path)

    async def send(self, message: ChannelMessage) -> ChannelResponse:
        """Send a push notification.

        Routes to Web Push or FCM based on recipient format.
        """
        if not self.is_available:
            return dry_run_send(self, message)

        recipient = message.recipient or ""

        # Route based on recipient prefix
        if recipient.startswith("fcm:"):
            return await send_via_fcm(self, message, recipient[4:])
        elif recipient.startswith("webpush:"):
            user_id = recipient[8:]
            return await send_via_web_push(self, message, user_id)

        # No prefix — try both backends, return first success
        responses: List[ChannelResponse] = []

        if self._has_fcm:
            fcm_resp = await send_via_fcm(self, message, recipient)
            if fcm_resp.success:
                return fcm_resp
            responses.append(fcm_resp)

        if self._has_web_push:
            wp_resp = await send_via_web_push(self, message, recipient)
            if wp_resp.success:
                return wp_resp
            responses.append(wp_resp)

        # Both failed or neither configured
        if responses:
            return responses[-1]

        return dry_run_send(self, message)

    async def send_confirmation(
        self, request: ConfirmationRequest,
    ) -> ChannelResponse:
        """Send confirmation as push notification with action options."""
        if not self.is_available:
            return dry_run_confirmation(self, request)

        # Build notification body with options
        option_labels = {
            "yes": "Confirm",
            "no": "Deny",
            "more_info": "More Info",
        }
        options_text = " | ".join(
            option_labels.get(o, o.replace("_", " ").title())
            for o in request.options
        )

        body = request.message
        if options_text:
            body = f"{body}\n\nActions: {options_text}" if body else f"Actions: {options_text}"

        # Build data payload with confirmation metadata
        data: Dict[str, Any] = {
            "type": "confirmation",
            "action_id": request.action_id,
            "action_type": request.action_type,
            "options": list(request.options),
            "timeout_seconds": request.timeout_seconds,
        }

        message = ChannelMessage(
            text=body,
            title=request.title or "Confirmation Required",
            recipient=request.recipient,
            metadata={
                **request.metadata,
                **data,
                "is_confirmation": True,
            },
        )

        response = await self.send(message)

        with self._lock:
            self._confirmation_count += 1

        return response

    async def start(self) -> None:
        """Initialize the provider (create HTTP session, load keys)."""
        if self._started:
            return

        if _HAS_AIOHTTP and not self._session:
            import aiohttp
            from ._utils import _HTTP_TIMEOUT
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=_HTTP_TIMEOUT),
            )

        # Pre-load VAPID private key
        if self._has_web_push and _HAS_CRYPTOGRAPHY:
            self._load_vapid_private_key()

        # Pre-load FCM service account data
        if self._has_fcm:
            self._load_fcm_service_account()

        self._started = True
        logger.info(
            "PushChannelProvider: started (webpush=%s, fcm=%s)",
            self._has_web_push,
            self._has_fcm,
        )

    async def stop(self) -> None:
        """Gracefully shut down the provider."""
        if self._session and _HAS_AIOHTTP:
            await self._session.close()
            self._session = None

        self._started = False
        logger.info("PushChannelProvider: stopped")

    @property
    def stats(self) -> Dict[str, Any]:
        """Provider statistics."""
        with self._lock:
            return {
                "name": "push",
                "sent_count": self._sent_count,
                "failed_count": self._failed_count,
                "confirmation_count": self._confirmation_count,
                "webpush_sent": self._webpush_sent,
                "fcm_sent": self._fcm_sent,
                "is_available": self.is_available,
                "has_web_push": self._has_web_push,
                "has_fcm": self._has_fcm,
                "subscription_count": len(self._subscriptions),
                "started": self._started,
            }

    @property
    def rate_limit_info(self) -> RateLimitInfo:
        """Current rate limit status."""
        return self._rate_limit_info

    # ── Web Push Subscription Management ────────────────────────

    def register_subscription(
        self, user_id: str, subscription: Dict[str, Any],
    ) -> None:
        """Register a Web Push subscription for a user."""
        return register_subscription(self, user_id, subscription)

    def unregister_subscription(self, user_id: str) -> bool:
        """Remove a Web Push subscription."""
        return unregister_subscription(self, user_id)

    def get_subscription(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a Web Push subscription for a user."""
        return get_subscription(self, user_id)

    # ── FCM Public Methods ──────────────────────────────────────

    async def send_fcm(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> ChannelResponse:
        """Send an FCM push notification to a specific device token."""
        return await send_fcm_message(self, token, title, body, data)

    async def send_fcm_to_topic(
        self,
        topic: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> ChannelResponse:
        """Send an FCM push notification to a topic."""
        return await send_fcm_to_topic(self, topic, title, body, data)

    # ── Web Push Public Methods ─────────────────────────────────

    async def send_web_push(
        self,
        user_id: str,
        payload: Dict[str, Any],
    ) -> ChannelResponse:
        """Send a Web Push notification to a registered user."""
        return await send_web_push_message(self, user_id, payload)


__all__ = ["PushChannelProvider"]
