"""ZENIC-AGENTS - Channel Formatter: Text Processing"""

from __future__ import annotations

def truncate(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to max_length, appending suffix if truncated."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def split_message(text: str, max_length: int, overlap: int = 0) -> List[str]:
    """Split long text into chunks respecting paragraph/line/word boundaries.

    Strategy (in order of preference):
      1. Split on double-newline (paragraph boundary)
      2. Split on single newline (line boundary)
      3. Split on space (word boundary)
      4. Hard split at max_length

    Args:
        text: The text to split.
        max_length: Maximum length per chunk.
        overlap: Number of characters to overlap between chunks (for context).

    Returns:
        List of text chunks, each <= max_length.
    """
    if len(text) <= max_length:
        return [text]

    chunks: List[str] = []

    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        # Find best split point within max_length
        split_at = max_length

        # Try paragraph boundary
        para_pos = text.rfind("\n\n", 0, max_length)
        if para_pos > max_length * 0.3:
            split_at = para_pos + 2
        else:
            # Try line boundary
            line_pos = text.rfind("\n", 0, max_length)
            if line_pos > max_length * 0.3:
                split_at = line_pos + 1
            else:
                # Try word boundary
                space_pos = text.rfind(" ", 0, max_length)
                if space_pos > max_length * 0.3:
                    split_at = space_pos + 1

        chunks.append(text[:split_at])
        text = text[split_at - overlap:] if overlap else text[split_at:]

    return chunks


def sanitize_plain_text(text: str) -> str:
    """Strip ANSI codes, control chars, and collapse whitespace."""
    # Remove ANSI escape sequences
    text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
    # Remove control characters except newline/tab
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Collapse multiple spaces (not newlines)
    text = re.sub(r"[^\S\n]+", " ", text)
    return text.strip()


def sanitize_html(text: str) -> str:
    """Remove script tags and escape HTML entities."""
    # Remove script tags
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.IGNORECASE | re.DOTALL)
    # Remove event handlers
    text = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', "", text, flags=re.IGNORECASE)
    return text


# ──────────────────────────────────────────────────────────────
#  TELEGRAM FORMATTING
# ──────────────────────────────────────────────────────────────

# MarkdownV2 special characters that must be escaped
