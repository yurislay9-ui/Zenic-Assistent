"""
ZENIC-AGENTS — Adapter Registry Types

Routing constants and type aliases for the channel registry.
"""

from __future__ import annotations

from typing import Dict, List

from .._types import ChannelPriority

# Priority → channel suitability mapping
_PRIORITY_CHANNEL_MAP: Dict[ChannelPriority, List[str]] = {
    ChannelPriority.LOW: ["log", "email", "push"],
    ChannelPriority.NORMAL: ["log", "email", "push", "teams", "slack"],
    ChannelPriority.HIGH: ["email", "push", "teams", "slack", "sms"],
    ChannelPriority.URGENT: ["sms", "push", "teams", "slack", "email"],
    ChannelPriority.EMERGENCY: ["sms", "whatsapp", "push", "teams", "slack", "email"],
}

# Default fallback chains
_DEFAULT_FALLBACKS: Dict[str, List[str]] = {
    "teams": ["email", "log"],
    "slack": ["email", "log"],
    "whatsapp": ["sms", "email", "log"],
    "sms": ["email", "log"],
    "email": ["push", "log"],
    "push": ["email", "log"],
    "log": [],
}
