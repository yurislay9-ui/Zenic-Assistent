"""
Tests for cross-niche analysis, stats, and singleton behavior.
"""

import pytest
import threading

from src.core.niche_loader import (
    NicheLoader, NicheTemplate, YAML_AVAILABLE,
    get_niche_loader,
)


# ============================================================
#  Cross-Niche Analysis Tests
# ============================================================

class TestCrossNicheAnalysis:
    """Tests for cross-niche block and entity frequency analysis."""

    def test_get_common_blocks(self, loaded_niche_loader):
        """Should return block frequency across niches."""
        blocks = loaded_niche_loader.get_common_blocks()
        assert "crud_service" in blocks
        assert blocks["crud_service"] == 2  # Both niches use crud_service

    def test_get_common_entities(self, loaded_niche_loader):
        """Should return entity name frequency across niches."""
        entities = loaded_niche_loader.get_common_entities()
        # Each niche has unique entity names
        assert len(entities) > 0

    def test_get_domain_overview(self, loaded_niche_loader):
        """Should return overview with statistics per domain."""
        overview = loaded_niche_loader.get_domain_overview()
        assert "healthcare" in overview
        assert overview["healthcare"]["niche_count"] >= 1
        assert overview["healthcare"]["total_entities"] >= 1


# ============================================================
#  Stats Tests
# ============================================================

class TestNicheLoaderStats:
    """Tests for NicheLoader stats property."""

    def test_stats_structure(self, loaded_niche_loader):
        """Stats should contain expected keys."""
        stats = loaded_niche_loader.stats
        assert "total_niches" in stats
        assert "total_domains" in stats
        assert "yaml_available" in stats
        assert "loaded" in stats

    def test_stats_auto_loads(self, niche_loader):
        """Stats should trigger auto-load if not loaded."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        assert not niche_loader._loaded
        stats = niche_loader.stats
        assert niche_loader._loaded

    def test_stats_niche_count(self, loaded_niche_loader):
        """Should report correct number of loaded niches."""
        stats = loaded_niche_loader.stats
        assert stats["total_niches"] >= 2


# ============================================================
#  Singleton Tests
# ============================================================

class TestNicheSingleton:
    """Tests for get_niche_loader singleton."""

    def test_singleton_returns_same_instance(self):
        """get_niche_loader should return the same instance."""
        import src.core.niche_loader as mod
        mod._niche_loader_instance = None
        loader1 = get_niche_loader()
        loader2 = get_niche_loader()
        assert loader1 is loader2
        mod._niche_loader_instance = None

    def test_singleton_is_niche_loader_type(self):
        """Singleton should be a NicheLoader instance."""
        import src.core.niche_loader as mod
        mod._niche_loader_instance = None
        loader = get_niche_loader()
        assert isinstance(loader, NicheLoader)
        mod._niche_loader_instance = None

    def test_singleton_thread_safe(self):
        """Singleton should be thread-safe."""
        import src.core.niche_loader as mod
        mod._niche_loader_instance = None
        results = []
        def get_loader():
            results.append(get_niche_loader())
        threads = [threading.Thread(target=get_loader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(r is results[0] for r in results)
        mod._niche_loader_instance = None
