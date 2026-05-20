"""
ZENIC-AGENTS — Microsoft Teams Channel Provider

Outbound: Incoming Webhooks with Adaptive Cards
Inbound:  Bot Framework (optional, for bidirectional)
"""

from ._mixin_core import TeamsChannelProvider

__all__ = ["TeamsChannelProvider"]
