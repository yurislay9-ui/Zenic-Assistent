"""
Zenic-Agents Conversational Adapters

Channel adapters for Telegram and Discord integration.
Both use aiohttp directly — no external bot libraries required.
"""

from .telegram import TelegramAdapter
from .discord import DiscordAdapter

__all__ = [
    "TelegramAdapter",
    "DiscordAdapter",
]
