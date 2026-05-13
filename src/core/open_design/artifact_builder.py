"""
Artifact Builder — wraps generated code in <artifact> XML tags.

Open Design expects code output wrapped in <artifact> tags with metadata.
This module provides utilities for building properly formatted artifacts
that Open Design can parse and render in its iframe.
"""

import re
import time
import uuid
import logging
from typing import Dict, Any, Optional, List
from xml.sax.saxutils import escape as xml_escape

from .config import get_open_design_config

logger = logging.getLogger(__name__)


class ArtifactBuilder:
    """
    Builds <artifact> wrapped output for Open Design compatibility.

    The artifact format expected by Open Design:

        <artifact identifier="name" type="application/vnd.ant.code"
                  language="html" title="Generated UI">
            <!-- code content here -->
        </artifact>

    Multiple artifacts can be included in a single response for
    multi-file generation (e.g., HTML + CSS + JS).
    """

    @staticmethod
    def build_artifact(
        code: str,
        identifier: Optional[str] = None,
        artifact_type: Optional[str] = None,
        language: str = "html",
        title: Optional[str] = None,
    ) -> str:
        """
        Wrap code in an <artifact> tag.

        Args:
            code: The generated code content.
            identifier: Unique identifier for the artifact (auto-generated if None).
            artifact_type: MIME type (default from config).
            language: Programming language for syntax highlighting.
            title: Human-readable title for the artifact.

        Returns:
            String with the code wrapped in <artifact>...</artifact> tags.
        """
        config = get_open_design_config()

        if identifier is None:
            identifier = f"artifact-{uuid.uuid4().hex[:8]}"

        if artifact_type is None:
            artifact_type = config.artifact_types.get(
                language, config.default_artifact_type
            )

        if title is None:
            title = f"Generated {language.upper()} Code"

        # Build the artifact tag with attributes
        # Note: We do NOT XML-escape the code content because Open Design
        # expects raw code inside <artifact>. The tag itself uses proper
        # attribute quoting.
        artifact = (
            f'<artifact identifier="{identifier}" '
            f'type="{artifact_type}" '
            f'language="{language}" '
            f'title="{title}">\n'
            f'{code}\n'
            f'</artifact>'
        )

        return artifact

    @staticmethod
    def build_multi_artifact(
        files: Dict[str, str],
        language_map: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Build multiple <artifact> tags for multi-file generation.

        Used by FractalGenerator to deliver complete project structures
        to Open Design in a single response.

        Args:
            files: Dict mapping filename → code content.
            language_map: Optional dict mapping filename → language override.

        Returns:
            String with all files wrapped in <artifact> tags.
        """
        config = get_open_design_config()
        language_map = language_map or {}

        artifacts: List[str] = []

        for filename, code in files.items():
            # Determine language from file extension
            lang = language_map.get(filename)
            if not lang:
                lang = ArtifactBuilder._language_from_filename(filename)

            # Determine MIME type
            artifact_type = config.artifact_types.get(
                lang, config.default_artifact_type
            )

            # Clean identifier from filename
            identifier = re.sub(r'[^a-zA-Z0-9_-]', '_', filename)

            artifact = ArtifactBuilder.build_artifact(
                code=code,
                identifier=identifier,
                artifact_type=artifact_type,
                language=lang,
                title=filename,
            )
            artifacts.append(artifact)

        return "\n\n".join(artifacts)

    @staticmethod
    def wrap_response_content(
        content: str,
        detection_result: Optional[Dict[str, Any]] = None,
        language: str = "html",
    ) -> str:
        """
        Conditionally wrap response content in <artifact> tags.

        Only wraps if:
        1. Open Design artifact wrapping is enabled in config
        2. The request was detected as coming from Open Design, OR
        3. The request was classified as a visual/UI request

        Args:
            content: The raw response content (may contain code blocks).
            detection_result: Result from OpenDesignDetector.detect().
            language: Default language for the artifact.

        Returns:
            Content either wrapped in <artifact> or as-is.
        """
        config = get_open_design_config()

        if not config.artifact_wrapping_enabled:
            return content

        # Only wrap if this is an Open Design or visual request
        if detection_result:
            if not (detection_result.get("is_open_design")
                    or detection_result.get("is_visual_request")):
                return content
        else:
            # No detection result — don't wrap
            return content

        # Extract code from markdown code blocks if present
        code_blocks = ArtifactBuilder._extract_code_blocks(content)

        if code_blocks:
            # Multiple code blocks → multiple artifacts
            artifacts = []
            for i, (lang, code) in enumerate(code_blocks):
                artifact = ArtifactBuilder.build_artifact(
                    code=code,
                    identifier=f"artifact-{i+1}",
                    language=lang or language,
                    title=f"Code Block {i+1}",
                )
                artifacts.append(artifact)

            # Preserve any non-code text as context before the artifacts
            non_code = ArtifactBuilder._extract_non_code_text(content)
            if non_code.strip():
                return non_code.strip() + "\n\n" + "\n\n".join(artifacts)
            return "\n\n".join(artifacts)

        # No code blocks found — wrap entire content as single artifact
        # (Only if it looks like code, not just explanation text)
        if ArtifactBuilder._looks_like_code(content):
            return ArtifactBuilder.build_artifact(
                code=content,
                language=language,
            )

        return content

    @staticmethod
    def _extract_code_blocks(text: str) -> List[tuple]:
        """Extract code blocks from markdown format: ```lang\\ncode\\n```"""
        pattern = re.compile(r'```(\w*)\n(.*?)```', re.DOTALL)
        return [(m.group(1), m.group(2).strip()) for m in pattern.finditer(text)]

    @staticmethod
    def _extract_non_code_text(text: str) -> str:
        """Remove code blocks from text, keeping surrounding content."""
        return re.sub(r'```(\w*)\n.*?```', '', text, flags=re.DOTALL)

    @staticmethod
    def _language_from_filename(filename: str) -> str:
        """Determine language from file extension."""
        ext_map = {
            ".py": "python", ".js": "javascript", ".jsx": "react",
            ".ts": "typescript", ".tsx": "react", ".html": "html",
            ".css": "css", ".scss": "css", ".json": "json",
            ".yaml": "yaml", ".yml": "yaml", ".md": "markdown",
            ".sql": "sql", ".sh": "bash", ".svg": "svg",
            ".vue": "vue", ".svelte": "svelte",
        }
        for ext, lang in ext_map.items():
            if filename.endswith(ext):
                return lang
        return "text"

    @staticmethod
    def _looks_like_code(text: str) -> bool:
        """Heuristic: check if text looks like code rather than prose."""
        code_indicators = [
            "def ", "class ", "function ", "import ", "from ",
            "const ", "let ", "var ", "return ", "if ", "for ",
            "<div", "<span", "<html", "<body", "<head",
            "{", "}", "=>", "->", "::",
        ]
        matches = sum(1 for indicator in code_indicators if indicator in text)
        return matches >= 3


def wrap_in_artifact(code: str, language: str = "html",
                     title: Optional[str] = None) -> str:
    """Convenience function: wrap code in a single <artifact> tag."""
    return ArtifactBuilder.build_artifact(
        code=code, language=language, title=title,
    )
