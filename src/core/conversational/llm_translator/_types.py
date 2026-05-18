"""Types and constants for llm_translator."""

from __future__ import annotations
import json
import logging
import re
import time

logger = logging.getLogger("zenic_agents.conversational.llm_translator")

VALID_INTENTS = frozenset({
    "chat", "question", "command", "config", "feedback",
    "code_create", "code_refactor", "code_debug", "code_optimize",
    "code_analyze", "code_explain", "business", "automation", "unknown",
})

VALID_ACTION_TYPES = frozenset({
    "CREATE", "REFACTOR", "DELETE", "SEARCH", "ANALYZE",
    "EXPLAIN", "DEBUG", "OPTIMIZE", "CHAT", "COMMAND",
    "CONFIG", "QUESTION",
})

INTENT_TO_ACTION = {
    "chat": "CHAT",
    "question": "SEARCH",
    "command": "COMMAND",
    "config": "CONFIG",
    "feedback": "CHAT",
    "code_create": "CREATE",
    "code_refactor": "REFACTOR",
    "code_debug": "DEBUG",
    "code_optimize": "OPTIMIZE",
    "code_analyze": "ANALYZE",
    "code_explain": "EXPLAIN",
    "business": "CHAT",
    "automation": "COMMAND",
    "unknown": "SEARCH",
}
