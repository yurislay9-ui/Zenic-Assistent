"""PostMixin - Shared imports and utilities."""

import json
import logging
import time

from .._imports import (
    _run_async, _REQUEST_TIMEOUT,
    build_normal_response,
    build_partial_reasoning_response,
    build_error_response,
    build_overloaded_response,
    build_artifact_response,
)

logger = logging.getLogger("zenic_agents.server.http_parts.post_mixin")

# Open Design Integration
try:
    from src.core.open_design import (
        OpenDesignDetector, SSEStreamer,
    )
    _OPEN_DESIGN_AVAILABLE = True
except ImportError:
    _OPEN_DESIGN_AVAILABLE = False


def _extract_msg_text(content):
    """Extract plain text from OpenAI message content.

    The OpenAI API allows 'content' to be either a string or a list of
    content parts (multimodal messages).  Cline and other tools send the
    list format, which caused: TypeError: can only concatenate list (not
    "str") to list.

    Args:
        content: str, list[dict], list[str], or None

    Returns:
        str — the concatenated text from the content field
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
        return " ".join(parts)
    return str(content)
