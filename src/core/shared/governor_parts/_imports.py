"""Shared imports and constants for governor_parts.

FIX (Phase 4): Removed unused imports (os, gc, time, threading, Any, Dict,
Optional) that are never consumed by child modules via `from ._imports import`.
Only `logger` and `resource` are actually shared across governor_parts modules.
"""

import logging

try:
    import resource
except ImportError:
    resource = None  # Not available on Android/Termux

logger = logging.getLogger(__name__)

__all__ = ["logger", "resource"]
