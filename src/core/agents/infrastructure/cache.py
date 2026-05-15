"""
ZENIC-AGENTS - AgentCache

Semantic cache for agent results.
Avoids repeated LLM calls for similar queries.

Migrated from agents/cache.py (v1 legacy) to agents/infrastructure/ as part
of the v1→v2 migration. This is the canonical location for AgentCache.
"""

import hashlib
import time
import threading
import logging
from collections import OrderedDict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cache configuration
MAX_CACHE_SIZE = 500          # Maximum cache entries
DEFAULT_TTL_SECONDS = 3600   # 1 hour TTL
SIMILARITY_THRESHOLD = 0.85  # Threshold for semantic cache hit


class AgentCache:
    """
    Agent result cache.

    Two lookup modes:
    1. Exact: SHA256 hash of input -> direct result
    2. Semantic: If SemanticEngine is available, uses embeddings

    The cache is deliberately simple to work on restricted hardware
    (Xiaomi Redmi 12R Pro, 12GB RAM).
    """

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS,
                 max_size: int = MAX_CACHE_SIZE) -> None:
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._hits = 0
        self._misses = 0
        self._semantic_engine = None
        self._lock = threading.Lock()

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / max(self._hits + self._misses, 1),
        }

    def set_semantic_engine(self, engine) -> None:
        """Wire the SemanticEngine for semantic cache."""
        self._semantic_engine = engine

    def get(self, agent_name: str, input_data: Any) -> Optional[Any]:
        """
        Look up in cache by agent and input.

        Args:
            agent_name: Agent name
            input_data: Input data

        Returns:
            Cached result or None
        """
        key = self._make_key(agent_name, input_data)

        # 1. Exact lookup (thread-safe)
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                if not self._is_expired(entry):
                    self._hits += 1
                    # Move to end for LRU behavior (most recently used at end)
                    self._cache.move_to_end(key)
                    return entry["result"]
                else:
                    # Expired, delete within lock
                    del self._cache[key]

        # 2. Semantic lookup (if engine is available)
        if self._semantic_engine and self._semantic_engine.is_loaded:
            sem_result = self._semantic_lookup(agent_name, input_data)
            if sem_result is not None:
                with self._lock:
                    self._hits += 1
                return sem_result

        with self._lock:
            self._misses += 1
        return None

    def put(self, agent_name: str, input_data: Any, result: Any) -> None:
        """
        Store a result in the cache.

        Args:
            agent_name: Agent name
            input_data: Input data
            result: Result to cache
        """
        key = self._make_key(agent_name, input_data)

        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)

            # Prevent cache from growing too large
            if len(self._cache) >= self._max_size:
                self._evict_oldest()

            self._cache[key] = {
                "agent": agent_name,
                "result": result,
                "timestamp": time.time(),
                "access_count": 0,
                "input_text": self._serialize(input_data)[:500],
            }

    def clear(self) -> None:
        """Clear the entire cache."""
        self._cache.clear()
        logger.debug("AgentCache: Cleared")

    def __len__(self) -> int:
        """Return the number of entries in the cache."""
        return len(self._cache)

    def _make_key(self, agent_name: str, input_data: Any) -> str:
        """Generate a hash key for the cache."""
        input_str = f"{agent_name}:{self._serialize(input_data)}"
        return hashlib.sha256(input_str.encode()).hexdigest()[:32]

    @staticmethod
    def _serialize(data: Any) -> str:
        """Serialize data for deterministic hashing."""
        import json
        if isinstance(data, str):
            return data
        if hasattr(data, '__dict__'):
            try:
                return json.dumps(data.__dict__, sort_keys=True, default=str)
            except (TypeError, ValueError):
                return str(data)
        return str(data)

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """Check if an entry has expired."""
        age = time.time() - entry.get("timestamp", 0)
        return age > self._ttl

    def _evict_oldest(self) -> None:
        """Evict the oldest entry (LRU) — O(1) with OrderedDict.

        OrderedDict maintains insertion order; oldest items are at the front.
        Since we move accessed items to the end via move_to_end(), this
        naturally implements LRU eviction.
        """
        if not self._cache:
            return
        # Pop the first (oldest/least recently used) item — O(1)
        self._cache.popitem(last=False)

    def _semantic_lookup(self, agent_name: str,
                         input_data: Any) -> Optional[Any]:
        """
        Look up in cache using semantic similarity.

        Only works if SemanticEngine is available.
        Compares the input with all cached inputs for the same agent.
        """
        if not self._semantic_engine or not self._semantic_engine.is_loaded:
            return None

        # Get input text
        input_text = str(input_data) if not isinstance(input_data, str) else input_data
        if not input_text or len(input_text) < 5:
            return None

        best_match = None
        best_score = 0.0

        for key, entry in self._cache.items():
            if entry.get("agent") != agent_name:
                continue
            if self._is_expired(entry):
                continue

            # Compare using SemanticEngine
            cached_input = entry.get("input_text", "")
            if not cached_input:
                continue

            try:
                score = self._semantic_engine.compute_similarity(input_text, cached_input)
                if score > best_score and score >= SIMILARITY_THRESHOLD:
                    best_score = score
                    best_match = entry["result"]
            except Exception:
                continue

        return best_match
