"""ZENIC-AGENTS - Channel Formatter: Platform Limits"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


class PlatformLimits:
    """Character/content limits per platform."""
    telegram_text: int = 4096
    telegram_caption: int = 1024
    discord_text: int = 2000
    discord_embed_title: int = 256
    discord_embed_description: int = 2048
    discord_embed_fields: int = 25
    discord_embed_field_name: int = 256
    discord_embed_field_value: int = 1024
    discord_embed_footer: int = 2048
    slack_text: int = 3000
    slack_block_text: int = 3000
    teams_text: int = 18000           # Adaptive Card body limit
    whatsapp_text: int = 4096
    sms_text: int = 160
    sms_mms_text: int = 1600


# Default singleton instance
LIMITS = PlatformLimits()