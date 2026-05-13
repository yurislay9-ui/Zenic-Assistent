"""Tests for importance scoring, embedding serialization, thread safety, and stats."""

import threading

import numpy as np

from src.core.smart_memory import SmartMemory


# ============================================================
#  Importance Scoring Tests
# ============================================================

class TestImportanceScoring:
    """Tests for compute_importance static method."""

    def test_base_score(self):
        """Default importance should be around 0.5."""
        score = SmartMemory.compute_importance("query", "EXPLAIN", "READABILITY",
                                                True, 100)
        assert 0.0 <= score <= 1.0

    def test_delete_operation_higher(self):
        """DELETE operation should score higher than EXPLAIN."""
        del_score = SmartMemory.compute_importance("q", "DELETE", "BUG_FIX",
                                                     True, 100)
        explain_score = SmartMemory.compute_importance("q", "EXPLAIN", "READABILITY",
                                                        True, 100)
        assert del_score > explain_score

    def test_security_goal_higher(self):
        """SECURITY_HARDEN goal should score higher than READABILITY."""
        sec_score = SmartMemory.compute_importance("q", "CREATE", "SECURITY_HARDEN",
                                                    True, 100)
        read_score = SmartMemory.compute_importance("q", "CREATE", "READABILITY",
                                                      True, 100)
        assert sec_score > read_score

    def test_long_response_bonus(self):
        """Long responses should get a small bonus."""
        short = SmartMemory.compute_importance("q", "CREATE", "FEATURE_ADD",
                                                True, 100)
        long = SmartMemory.compute_importance("q", "CREATE", "FEATURE_ADD",
                                               True, 2000)
        assert long > short

    def test_score_bounded(self):
        """Score should always be between 0.0 and 1.0."""
        # Push score very high
        score = SmartMemory.compute_importance("q", "DELETE", "SECURITY_HARDEN",
                                                True, 5000)
        assert score <= 1.0
        # Push score very low
        score = SmartMemory.compute_importance("q", "SEARCH", "MODERN_PATTERN",
                                                False, 10)
        assert score >= 0.0


# ============================================================
#  Embedding Serialization Tests
# ============================================================

class TestEmbeddingSerialization:
    """Tests for embedding serialize/deserialize round-trip."""

    def test_round_trip(self):
        """Should preserve embedding direction through serialization (normalizes on deserialize)."""
        emb = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        blob = SmartMemory._serialize_embedding(emb)
        result = SmartMemory._deserialize_embedding(blob)
        # _deserialize_embedding normalizes the vector, so check direction (cosine similarity)
        # rather than exact values
        norm_orig = emb / np.linalg.norm(emb)
        np.testing.assert_allclose(result, norm_orig, atol=1e-6)

    def test_deserialize_none(self):
        """Should return None for None input."""
        assert SmartMemory._deserialize_embedding(None) is None

    def test_deserialize_empty(self):
        """Should return None for empty bytes."""
        assert SmartMemory._deserialize_embedding(b"") is None


# ============================================================
#  Thread Safety Tests
# ============================================================

class TestThreadSafety:
    """Tests for thread safety of working memory operations."""

    def test_concurrent_add_working(self, memory):
        """Should handle concurrent additions safely."""
        errors = []

        def add_entries(start):
            try:
                for i in range(50):
                    memory.add_working(f"q_{start}_{i}", f"r_{start}_{i}",
                                       importance=0.5)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_entries, args=(j,)) for j in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(memory._working_memory) > 0

    def test_concurrent_cache_operations(self, memory):
        """Should handle concurrent cache save/check safely."""
        errors = []

        def cache_ops(thread_id):
            try:
                for i in range(20):
                    memory.save_to_cache(f"query_{thread_id}_{i}", f"resp_{i}",
                                         importance=0.5)
                    memory.check_cache(f"query_{thread_id}_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=cache_ops, args=(j,)) for j in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_episode_operations(self, memory):
        """Should handle concurrent episode save/find safely."""
        errors = []

        def episode_ops(thread_id):
            try:
                for i in range(10):
                    memory.save_episode(f"event_{thread_id}", f"desc_{i}",
                                         importance=0.5)
                memory.find_episodes(event_type=f"event_{thread_id}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=episode_ops, args=(j,)) for j in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# ============================================================
#  Stats Tests
# ============================================================

class TestStats:
    """Tests for stats and enhanced_stats properties."""

    def test_stats_structure(self, memory):
        """Stats should contain expected keys."""
        stats = memory.stats
        assert "session_id" in stats
        assert "client_id" in stats
        assert "working_memory_size" in stats
        assert "semantic_cache_size" in stats
        assert "long_term_memory_size" in stats

    def test_enhanced_stats_structure(self, memory):
        """Enhanced stats should contain all memory type counts."""
        stats = memory.enhanced_stats
        assert "working_memory_size" in stats
        assert "semantic_cache_size" in stats
        assert "episodic_memory_size" in stats
        assert "procedural_memory_size" in stats
        assert "project_memory_size" in stats

    def test_stats_reflects_working_memory(self, memory):
        """Working memory size should reflect added entries."""
        memory.add_working("q1", "r1")
        memory.add_working("q2", "r2")
        assert memory.stats["working_memory_size"] == 2
