"""Re-exports for sna_engine package."""

from ._types import *
from ._mixin_core import *

import asyncio
import logging
import time

def get_sna_engine() -> SNAEngine:
    """Get or create the global SNAEngine instance."""
    global _default_engine
    if _default_engine is None:
        _default_engine = SNAEngine()
    return _default_engine


def reset_sna_engine() -> None:
    """Reset the global SNAEngine (for testing)."""
    global _default_engine
    _default_engine = None

