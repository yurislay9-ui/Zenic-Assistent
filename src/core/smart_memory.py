"""
ZENIC-AGENTS - SmartMemory (Intelligent Memory for Qwen)

Thin facade that re-exports from the modularized memory_parts sub-package.
All implementation has been moved to:
  - memory_parts/types.py      — MemoryEntry dataclass + constants
  - memory_parts/database.py   — DB initialization, migration, connections mixin
  - memory_parts/cache.py      — Semantic cache + working memory mixin
  - memory_parts/longterm.py   — Long-term memory + similarity search mixin
  - memory_parts/episodes.py   — Episodes, patterns, projects mixin
  - memory_parts/memory.py     — SmartMemory class (combines all mixins)
"""

from .memory_parts import (
    SmartMemory,
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

__all__ = [
    "SmartMemory",
    "MemoryEntry",
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
    "HAS_NUMPY",
    "logger",
]
