"""
Open Design Request Detector.

Detects whether an incoming request originates from Open Design,
and whether it requires visual bypass routing (skip SMT/AC-3 solver).
"""

import re
import logging
from typing import Dict, Any, Optional, List, Union

from .config import get_open_design_config

logger = logging.getLogger(__name__)


class OpenDesignDetector:
    """
    Detects Open Design requests and classifies them for bypass routing.

    Detection signals:
    1. HTTP headers: X-Client: open-design, Origin matches known OD origins
    2. Message content: contains <artifact> tags, design system signatures
    3. Request metadata: stream=true, presence of design_system field
    """

    # Pattern to detect <artifact> tags in messages
    ARTIFACT_PATTERN = re.compile(r"<artifact\b[^>]*>", re.IGNORECASE)

    # Pattern to detect Open Design system prompt signatures
    DESIGN_SYSTEM_PATTERN = re.compile(
        r"(design[_-]?system|theme[_-]?config|color[_-]?palette|"
        r"typography[_-]?scale|spacing[_-]?system|token[_-]?system|"
        r"stripe[_-]?design|material[_-]?design|ant[_-]?design|"
        r"chakra|tailwind[_-]?config)",
        re.IGNORECASE,
    )

    # Pattern to detect UI/frontend keywords in messages
    UI_KEYWORDS_PATTERN = re.compile(
        r"(ui|frontend|component|layout|css|html|react|vue|angular|"
        r"tailwind|bootstrap|material|figma|render|widget|page|form|"
        r"button|card|modal|sidebar|navbar|dashboard|panel|dialog|"
        r"menu|toolbar|style|theme|animation|responsive|viewport|"
        r"interface|visual|screen|artifact)",
        re.IGNORECASE,
    )

    @staticmethod
    def _extract_text(content: Union[str, List, None]) -> str:
        """Extract plain text from OpenAI message content.

        OpenAI API allows content to be either:
        - A string: "Hello"
        - A list of content parts: [{"type": "text", "text": "Hello"}, ...]
        - None (rare, treated as empty)
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

    @classmethod
    def detect(cls, messages: List[Dict[str, str]],
               headers: Optional[Dict[str, str]] = None,
               body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Analyze a request and return detection result.

        Args:
            messages: Chat messages from the request body.
            headers: HTTP headers (lowercase keys).
            body: Full request body dict.

        Returns:
            Dict with:
                is_open_design: bool -- request originates from Open Design
                is_visual_request: bool -- request should use visual bypass
                has_design_system: bool -- request contains design system data
                has_artifact: bool -- message contains <artifact> tags
                bypass_solver: bool -- should skip Z3/AC-3 solver
                context_budget_multiplier: float -- budget multiplier for context
                detection_signals: List[str] -- which signals triggered detection
        """
        config = get_open_design_config()
        headers = headers or {}
        body = body or {}

        signals: List[str] = []
        is_open_design = False
        is_visual_request = False
        has_design_system = False
        has_artifact = False

        # -- Signal 1: HTTP Headers --
        # Check for explicit Open Design client header
        if headers.get("x-client", "") == "open-design":
            is_open_design = True
            signals.append("header:x-client=open-design")

        # Check Origin header against known Open Design origins
        origin = headers.get("origin", "")
        if origin and origin in config.open_design_origins:
            is_open_design = True
            signals.append(f"header:origin={origin}")

        # Check User-Agent for Open Design
        ua = headers.get("user-agent", "").lower()
        if "open-design" in ua or "opendesign" in ua:
            is_open_design = True
            signals.append("header:user-agent")

        # -- Signal 2: Request body metadata --
        # Open Design sends stream=true for real-time rendering
        if body.get("stream", False):
            signals.append("body:stream=true")

        # Open Design includes design_system in request
        if body.get("design_system") or body.get("designSystem"):
            has_design_system = True
            is_visual_request = True
            signals.append("body:design_system")

        # Open Design includes visual_context in request
        if body.get("visual_context") or body.get("visualContext"):
            is_visual_request = True
            signals.append("body:visual_context")

        # -- Signal 3: Message content analysis --
        user_message = ""
        all_content = ""
        for msg in messages:
            content = msg.get("content", "")
            text = cls._extract_text(content)
            all_content += text + " "
            if msg.get("role") == "user":
                user_message += text + " "

        # Check for <artifact> tags
        if cls.ARTIFACT_PATTERN.search(all_content):
            has_artifact = True
            is_visual_request = True
            signals.append("content:artifact_tag")

        # Check for Design System signatures
        if cls.DESIGN_SYSTEM_PATTERN.search(all_content):
            has_design_system = True
            is_visual_request = True
            signals.append("content:design_system")

        # Check for UI/frontend keywords
        if config.visual_bypass_enabled:
            keyword_matches = cls.UI_KEYWORDS_PATTERN.findall(user_message.lower())
            if len(keyword_matches) >= 2:
                is_visual_request = True
                signals.append(f"content:ui_keywords({len(keyword_matches)})")

        # -- Determine bypass --
        bypass_solver = False
        if is_visual_request and config.visual_bypass_enabled:
            bypass_solver = True

        context_budget_multiplier = 1.0
        if has_design_system and config.preserve_design_systems:
            context_budget_multiplier = config.design_system_budget_multiplier

        result = {
            "is_open_design": is_open_design,
            "is_visual_request": is_visual_request,
            "has_design_system": has_design_system,
            "has_artifact": has_artifact,
            "bypass_solver": bypass_solver,
            "context_budget_multiplier": context_budget_multiplier,
            "detection_signals": signals,
        }

        if signals:
            logger.debug(
                "OpenDesign: detection result -- OD=%s visual=%s DS=%s "
                "bypass=%s signals=%s",
                is_open_design, is_visual_request, has_design_system,
                bypass_solver, signals,
            )

        return result


def is_open_design_request(messages: List[Dict[str, str]],
                            headers: Optional[Dict[str, str]] = None,
                            body: Optional[Dict[str, Any]] = None) -> bool:
    """Convenience function: returns True if request is from Open Design."""
    result = OpenDesignDetector.detect(messages, headers, body)
    return result["is_open_design"] or result["is_visual_request"]
