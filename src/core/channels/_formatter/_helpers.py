"""ZENIC-AGENTS - Channel Formatter: Helpers"""

from __future__ import annotations

def _store_and_replace(match: re.Match, store: List[str]) -> str:
    """Store a regex match and return a placeholder."""
    idx = len(store)
    store.append(match.group(0))
    return f"__CODE_BLOCK_{idx}__"


def _parse_color(color: str) -> int:
    """Parse a color string to Discord integer color.

    Accepts: hex (#RRGGBB, RRGGBB), named colors, or integer strings.
    """
    color = color.strip()

    # Hex
    if color.startswith("#"):
        return int(color[1:], 16)
    if color.startswith("0x"):
        return int(color[2:], 16)

    # Named colors
    named = {
        "red": 0xFF0000, "green": 0x00FF00, "blue": 0x0000FF,
        "yellow": 0xFFFF00, "orange": 0xFFA500, "purple": 0x800080,
        "cyan": 0x00FFFF, "white": 0xFFFFFF, "black": 0x000000,
        "gray": 0x808080, "grey": 0x808080,
    }
    if color.lower() in named:
        return named[color.lower()]

    # Try integer
    try:
        return int(color)
    except ValueError:
        return 0x5865F2  # Default: Blurple


# ──────────────────────────────────────────────────────────────
#  PUBLIC EXPORTS
# ──────────────────────────────────────────────────────────────
