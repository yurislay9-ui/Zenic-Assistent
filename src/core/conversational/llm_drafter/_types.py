"""Types and constants for llm_drafter."""

from __future__ import annotations
import logging
import re
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("zenic_agents.conversational.llm_drafter")

# Personalities:
PERSONALITY_PROMPTS: Dict[str, str] = {
    "zenic": (
        "You are Zenic, a professional and helpful AI coding assistant. "
        "You explain things clearly and concisely. You are thorough but not verbose."
    ),
    "logic": (
        "You are Logic, a precise and analytical AI assistant. "
        "You focus on accuracy and technical correctness. "
        "Provide structured, factual responses."
    ),
    "nova": (
        "You are Nova, a friendly and enthusiastic AI assistant. "
        "You make technical topics approachable and fun. "
        "Use casual language and emojis occasionally."
    ),
}

# Channels:
CHANNEL_FORMATTERS = {
    "telegram": True,
    "discord": True,
    "web": True,
    "cli": False,
}
