"""
ZENIC-AGENTS — Single source of truth for version information.

All version references should import from this module:
    from src.core.shared._version import ZENIC_VERSION, ZENIC_VERSION_STR

This avoids inconsistencies between main.py, main_headless.py,
install_termux.sh, and README.md.
"""

ZENIC_VERSION: str = "3.0.0"
"""Numeric version string (e.g. '3.0.0')."""

ZENIC_VERSION_STR: str = f"v{ZENIC_VERSION}"
"""Prefixed version string (e.g. 'v3.0.0')."""

ZENIC_FULL_NAME: str = f"ZENIC-AGENTS {ZENIC_VERSION_STR}"
"""Full product name with version (e.g. 'ZENIC-AGENTS v3.0.0')."""
