"""
ZENIC-AGENTS - SmartMemory Sub-package

Re-exports all public symbols from the modularized SmartMemory components.
"""

from .types import (
    MemoryEntry,
    DB_DIR,
    DB_PATH,
    MAX_WORKING_ENTRIES,
    MAX_COMPRESSED_TOKENS,
    IMPORTANCE_THRESHOLD,
    SEMANTIC_CACHE_THRESHOLD,
    MAX_LONG_TERM_ENTRIES,
    MAX_EPISODIC_ENTRIES,
    MAX_PROCEDURAL_ENTRIES,
    MAX_PROJECT_ENTRIES,
    HAS_NUMPY,
    logger,
)
from .database import DatabaseMixin
from .cache import CacheMixin
from .longterm import LongTermMixin
from .episodes import EpisodesMixin
from .memory import SmartMemory

__all__ = [
    # Main class
    "SmartMemory",
    # Data types
    "MemoryEntry",
    # Mixins
    "DatabaseMixin",
    "CacheMixin",
    "LongTermMixin",
    "EpisodesMixin",
    # Constants
    "DB_DIR",
    "DB_PATH",
    "MAX_WORKING_ENTRIES",
    "MAX_COMPRESSED_TOKENS",
    "IMPORTANCE_THRESHOLD",
    "SEMANTIC_CACHE_THRESHOLD",
    "MAX_LONG_TERM_ENTRIES",
    "MAX_EPISODIC_ENTRIES",
    "MAX_PROCEDURAL_ENTRIES",
    "MAX_PROJECT_ENTRIES",
    # Module-level flags
    "HAS_NUMPY",
    # Logger
    "logger",
]
