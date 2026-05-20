"""
ZENIC-AGENTS — Push Notifications Channel Provider

This package provides Web Push (VAPID) and Firebase Cloud Messaging (FCM)
push notification capabilities.

Backward-compatible import: ``from ..channels.providers.push import PushChannelProvider``
"""

from .provider import PushChannelProvider

__all__ = ["PushChannelProvider"]
