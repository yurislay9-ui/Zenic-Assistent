from __future__ import annotations

try:
    from .types import MemoryTier, MemoryType, MemoryRecord, MemoryQuery, MemorySearchResult, ContextWindow
except ImportError:
    MemoryTier = None  # type: ignore[misc,assignment]
    MemoryType = None  # type: ignore[misc,assignment]
    MemoryRecord = None  # type: ignore[misc,assignment]
    MemoryQuery = None  # type: ignore[misc,assignment]
    MemorySearchResult = None  # type: ignore[misc,assignment]
    ContextWindow = None  # type: ignore[misc,assignment]

try:
    from .engine import MemoryEngineV2, get_memory_engine_v2, reset_memory_engine_v2
except ImportError:
    MemoryEngineV2 = None  # type: ignore[misc,assignment]
    get_memory_engine_v2 = None  # type: ignore[misc,assignment]
    reset_memory_engine_v2 = None  # type: ignore[misc,assignment]

try:
    from .context_manager import ContextManager, get_context_manager, reset_context_manager
except ImportError:
    ContextManager = None  # type: ignore[misc,assignment]
    get_context_manager = None  # type: ignore[misc,assignment]
    reset_context_manager = None  # type: ignore[misc,assignment]

__all__ = [
    "MemoryTier",
    "MemoryType",
    "MemoryRecord",
    "MemoryQuery",
    "MemorySearchResult",
    "ContextWindow",
    "MemoryEngineV2",
    "get_memory_engine_v2",
    "reset_memory_engine_v2",
    "ContextManager",
    "get_context_manager",
    "reset_context_manager",
]
