"""
ZENIC-AGENTS — Slack Channel Provider

Outbound: Web API (chat.postMessage) with Block Kit
Inbound:  Events API (HTTP) or Socket Mode (WebSocket)
"""

from ._mixin_core import SlackChannelProvider

__all__ = ["SlackChannelProvider"]
