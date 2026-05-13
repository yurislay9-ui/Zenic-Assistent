"""
Unit tests for AgentCache

Tests exact hit/miss, LRU eviction, TTL expiration, semantic search,
and thread safety.
"""

import time
import threading
import pytest
from unittest.mock import MagicMock, patch

from src.core.agents.cache import AgentCache, MAX_CACHE_SIZE, DEFAULT_TTL_SECONDS, SIMILARITY_THRESHOLD


class TestAgentCachePutGet:
    """Tests for basic put/get operations."""

    def test_put_and_get_exact_hit(self):
        """Should retrieve a cached result with exact key match."""
        cache = AgentCache()
        cache.put("agent_a", "hello", {"result": "world"})
        result = cache.get("agent_a", "hello")
        assert result == {"result": "world"}

    def test_get_returns_none_on_miss(self):
        """Should return None for a key not in cache."""
        cache = AgentCache()
        result = cache.get("agent_a", "missing")
        assert result is None

    def test_different_agent_names_different_keys(self):
        """Same input data but different agent names should be separate keys."""
        cache = AgentCache()
        cache.put("agent_a", "input", "result_a")
        cache.put("agent_b", "input", "result_b")
        assert cache.get("agent_a", "input") == "result_a"
        assert cache.get("agent_b", "input") == "result_b"

    def test_overwrite_existing_key(self):
        """Putting the same key again should overwrite the old value."""
        cache = AgentCache()
        cache.put("agent", "key", "old")
        cache.put("agent", "key", "new")
        assert cache.get("agent", "key") == "new"


class TestAgentCacheStats:
    """Tests for cache hit/miss statistics."""

    def test_initial_stats(self):
        """Stats should be zeroed on init."""
        cache = AgentCache()
        stats = cache.stats
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0.0

    def test_hit_rate_after_operations(self):
        """Hit rate should be computed correctly."""
        cache = AgentCache()
        cache.put("agent", "k1", "v1")
        cache.get("agent", "k1")   # hit
        cache.get("agent", "k2")   # miss
        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5


class TestAgentCacheTTLExpiration:
    """Tests for TTL-based expiration."""

    def test_entry_expires_after_ttl(self):
        """An entry should not be returned after TTL expires."""
        cache = AgentCache(ttl_seconds=0)  # Immediate expiration
        cache.put("agent", "key", "value")
        # Even immediately, ttl=0 means the entry is already expired
        result = cache.get("agent", "key")
        assert result is None

    def test_entry_valid_within_ttl(self):
        """An entry should be returned when within TTL."""
        cache = AgentCache(ttl_seconds=3600)
        cache.put("agent", "key", "value")
        result = cache.get("agent", "key")
        assert result == "value"

    def test_is_expired_logic(self):
        """_is_expired should detect stale entries."""
        cache = AgentCache(ttl_seconds=1)
        cache.put("agent", "key", "value")
        entry = cache._cache[list(cache._cache.keys())[0]]
        # Not expired yet
        assert cache._is_expired(entry) is False
        # Simulate aging
        entry["timestamp"] = time.time() - 10
        assert cache._is_expired(entry) is True


class TestAgentCacheLRUEviction:
    """Tests for LRU eviction when cache is full."""

    def test_eviction_when_full(self):
        """Should evict the oldest entry when max_size is reached."""
        cache = AgentCache(max_size=3)
        cache.put("agent", "k1", "v1")
        cache.put("agent", "k2", "v2")
        cache.put("agent", "k3", "v3")
        # Cache is full; adding a 4th should evict k1
        cache.put("agent", "k4", "v4")
        assert cache.get("agent", "k1") is None  # evicted
        assert cache.get("agent", "k2") == "v2"
        assert cache.get("agent", "k4") == "v4"

    def test_lru_access_moves_to_end(self):
        """Accessing an entry should move it to the end (most recently used)."""
        cache = AgentCache(max_size=3)
        cache.put("agent", "k1", "v1")
        cache.put("agent", "k2", "v2")
        cache.put("agent", "k3", "v3")
        # Access k1 → moves to end
        cache.get("agent", "k1")
        # Now k2 is the LRU entry. Adding k4 should evict k2
        cache.put("agent", "k4", "v4")
        assert cache.get("agent", "k2") is None  # evicted
        assert cache.get("agent", "k1") == "v1"  # still present

    def test_len_reflects_cache_size(self):
        """__len__ should return the current number of entries."""
        cache = AgentCache(max_size=10)
        cache.put("agent", "k1", "v1")
        cache.put("agent", "k2", "v2")
        assert len(cache) == 2


class TestAgentCacheSemanticLookup:
    """Tests for semantic search functionality."""

    def test_semantic_lookup_with_engine(self):
        """Should use SemanticEngine for fuzzy matching when available."""
        cache = AgentCache()
        # Set up mock semantic engine
        mock_engine = MagicMock()
        mock_engine.is_loaded = True
        mock_engine.compute_similarity.return_value = 0.9  # Above threshold
        cache.set_semantic_engine(mock_engine)

        # Store entry with enough input_text
        cache.put("agent", "how to sort a list", {"result": "use sorted()"})
        # Clear the exact key so we only test semantic lookup
        cache._cache.clear()
        # Re-add with direct key manipulation for semantic test
        key = cache._make_key("agent", "how to sort a list")
        cache._cache[key] = {
            "agent": "agent",
            "result": {"result": "use sorted()"},
            "timestamp": time.time(),
            "access_count": 0,
            "input_text": "how to sort a list",
        }

        # Search with similar but not identical input
        result = cache.get("agent", "how can I sort a list?")
        # The semantic engine should have been called
        assert result is not None

    def test_semantic_lookup_skipped_when_engine_not_loaded(self):
        """Should skip semantic lookup when engine is not loaded."""
        cache = AgentCache()
        mock_engine = MagicMock()
        mock_engine.is_loaded = False
        cache.set_semantic_engine(mock_engine)

        cache.put("agent", "test input", "test result")
        # Exact key won't match, so it's a miss
        result = cache.get("agent", "different input")
        assert result is None
        mock_engine.compute_similarity.assert_not_called()

    def test_semantic_lookup_below_threshold(self):
        """Should return None when similarity is below threshold."""
        cache = AgentCache()
        mock_engine = MagicMock()
        mock_engine.is_loaded = True
        mock_engine.compute_similarity.return_value = 0.5  # Below 0.85 threshold
        cache.set_semantic_engine(mock_engine)

        key = cache._make_key("agent", "some input")
        cache._cache[key] = {
            "agent": "agent",
            "result": "cached",
            "timestamp": time.time(),
            "access_count": 0,
            "input_text": "some input",
        }

        result = cache.get("agent", "totally different")
        assert result is None


class TestAgentCacheClear:
    """Tests for cache clearing."""

    def test_clear_empties_cache(self):
        """Should remove all entries from the cache."""
        cache = AgentCache()
        cache.put("agent", "k1", "v1")
        cache.put("agent", "k2", "v2")
        cache.clear()
        assert len(cache) == 0
        assert cache.get("agent", "k1") is None

    def test_clear_resets_size_but_not_hits_misses(self):
        """Clear resets size but not hit/miss counters."""
        cache = AgentCache()
        cache.put("agent", "k1", "v1")
        cache.get("agent", "k1")   # hit
        cache.clear()
        assert cache.stats["size"] == 0
        # Hits/misses persist across clears (design choice)
        assert cache.stats["hits"] == 1


class TestAgentCacheSerialize:
    """Tests for the _serialize static method."""

    def test_serialize_string(self):
        """Should return string as-is."""
        assert AgentCache._serialize("hello") == "hello"

    def test_serialize_object_with_dict(self):
        """Should serialize objects with __dict__ as JSON."""
        class Obj:
            def __init__(self):
                self.x = 1
                self.y = "two"
        result = AgentCache._serialize(Obj())
        import json
        parsed = json.loads(result)
        assert parsed["x"] == 1
        assert parsed["y"] == "two"

    def test_serialize_primitive(self):
        """Should fall back to str() for primitives."""
        assert AgentCache._serialize(42) == "42"
        assert AgentCache._serialize(3.14) == "3.14"


class TestAgentCacheThreadSafety:
    """Tests for thread safety of cache operations."""

    def test_concurrent_put_and_get(self):
        """Should handle concurrent puts and gets without errors."""
        cache = AgentCache(max_size=1000)
        errors = []

        def writer():
            try:
                for i in range(200):
                    cache.put("agent", f"key_{i}", f"value_{i}")
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for i in range(200):
                    cache.get("agent", f"key_{i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
