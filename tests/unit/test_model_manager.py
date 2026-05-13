"""
ZENIC-AGENTS - ModelManager Tests

Tests for the hybrid lazy-loading model manager:
  - Lazy loading: models load only when first accessed
  - Auto-unload: models unload after idle timeout
  - Model swap: dynamic load/unload based on RAM budget
  - RAM budget enforcement
  - Singleton management
"""

import time
import threading
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.core.model_manager import (
    ModelManager,
    get_model_manager,
    init_model_manager,
    ENABLE_AUTO_UNLOAD,
)


# ============================================================
#  FIXTURES
# ============================================================

@pytest.fixture
def mock_semantic_engine():
    """Create a mock SemanticEngine."""
    engine = MagicMock()
    engine.is_loaded = True
    engine.unload_model = MagicMock()
    return engine


@pytest.fixture
def mock_ai_engine():
    """Create a mock MiniAIEngine."""
    engine = MagicMock()
    engine.is_loaded = True
    engine.unload_model = MagicMock()
    return engine


@pytest.fixture
def manager(mock_semantic_engine, mock_ai_engine):
    """Create a ModelManager with mocked model imports."""
    with patch.dict("sys.modules", {
        "src.core.semantic_engine": MagicMock(SemanticEngine=MagicMock(return_value=mock_semantic_engine)),
        "src.core.mini_ai_engine": MagicMock(MiniAIEngine=MagicMock(return_value=mock_ai_engine)),
    }):
        mgr = ModelManager(lazy_load=True, idle_timeout_s=300, ram_budget_mb=768)
        yield mgr


@pytest.fixture(autouse=True)
def reset_global_singleton():
    """Reset the global singleton between tests."""
    import src.core.model_manager as mm
    mm._manager = None
    yield
    mm._manager = None


# ============================================================
#  LAZY LOADING TESTS
# ============================================================

class TestLazyLoading:
    """Tests for lazy loading behaviour of ModelManager."""

    def test_models_not_loaded_on_init(self, manager):
        """Models should NOT be loaded when ModelManager is created."""
        assert manager._semantic_engine is None
        assert manager._mini_ai_engine is None
        assert manager.semantic_loaded is False
        assert manager.ai_loaded is False

    def test_semantic_engine_lazy_loads_on_access(self, manager, mock_semantic_engine):
        """Accessing semantic_engine property triggers lazy load."""
        with patch("src.core.model_manager.ModelManager._get_current_ram_mb", return_value=50.0):
            with patch("src.core.model_manager.ModelManager._check_ram_budget", return_value=True):
                # Patch the import inside _ensure_semantic_loaded
                with patch("src.core.semantic_engine.SemanticEngine", return_value=mock_semantic_engine):
                    engine = manager.semantic_engine
                    assert engine is not None
                    assert manager._stats["semantic_loads"] == 1

    def test_ai_engine_lazy_loads_on_access(self, manager, mock_ai_engine):
        """Accessing mini_ai_engine property triggers lazy load."""
        with patch("src.core.model_manager.ModelManager._get_current_ram_mb", return_value=50.0):
            with patch("src.core.model_manager.ModelManager._check_ram_budget", return_value=True):
                with patch("src.core.mini_ai_engine.MiniAIEngine", return_value=mock_ai_engine):
                    engine = manager.mini_ai_engine
                    assert engine is not None
                    assert manager._stats["ai_loads"] == 1

    def test_semantic_engine_ctx_lazy_loads(self, manager, mock_semantic_engine):
        """Context manager access also triggers lazy load."""
        with patch("src.core.model_manager.ModelManager._get_current_ram_mb", return_value=50.0):
            with patch("src.core.model_manager.ModelManager._check_ram_budget", return_value=True):
                with patch("src.core.semantic_engine.SemanticEngine", return_value=mock_semantic_engine):
                    with manager.semantic_engine_ctx() as engine:
                        assert engine is not None
                    assert manager._stats["semantic_loads"] == 1

    def test_eager_init_loads_both(self, manager, mock_semantic_engine, mock_ai_engine):
        """init_eager() should load both models immediately."""
        with patch("src.core.model_manager.ModelManager._get_current_ram_mb", return_value=50.0):
            with patch("src.core.model_manager.ModelManager._check_ram_budget", return_value=True):
                with patch("src.core.semantic_engine.SemanticEngine", return_value=mock_semantic_engine), \
                     patch("src.core.mini_ai_engine.MiniAIEngine", return_value=mock_ai_engine):
                    manager.init_eager()
                    assert manager._stats["semantic_loads"] >= 1
                    assert manager._stats["ai_loads"] >= 1

    def test_no_double_load_if_already_loaded(self, manager, mock_semantic_engine):
        """If model is already loaded, accessing it should not trigger another load."""
        manager._semantic_engine = mock_semantic_engine
        manager._semantic_last_access = time.time()
        manager._stats["semantic_loads"] = 0

        engine = manager.semantic_engine
        assert engine is mock_semantic_engine
        assert manager._stats["semantic_loads"] == 0  # No additional load


# ============================================================
#  AUTO-UNLOAD TESTS
# ============================================================

class TestAutoUnload:
    """Tests for auto-unload of idle models."""

    def test_unload_semantic(self, manager, mock_semantic_engine):
        """unload_semantic should call unload_model on the semantic engine."""
        manager._semantic_engine = mock_semantic_engine
        manager.unload_semantic(reason="manual")
        mock_semantic_engine.unload_model.assert_called_once()
        assert manager._stats["semantic_unloads"] == 1

    def test_unload_ai(self, manager, mock_ai_engine):
        """unload_ai should call unload_model on the AI engine."""
        manager._mini_ai_engine = mock_ai_engine
        manager.unload_ai(reason="manual")
        mock_ai_engine.unload_model.assert_called_once()
        assert manager._stats["ai_unloads"] == 1

    def test_unload_all(self, manager, mock_semantic_engine, mock_ai_engine):
        """unload_all should unload both models."""
        manager._semantic_engine = mock_semantic_engine
        manager._mini_ai_engine = mock_ai_engine
        manager.unload_all(reason="shutdown")
        mock_semantic_engine.unload_model.assert_called_once()
        mock_ai_engine.unload_model.assert_called_once()

    def test_unload_semantic_when_none(self, manager):
        """unload_semantic on None engine should be a no-op."""
        manager._semantic_engine = None
        manager.unload_semantic()  # Should not raise
        assert manager._stats["semantic_unloads"] == 0

    def test_check_idle_unload_expires_semantic(self, manager, mock_semantic_engine):
        """Semantic engine should be unloaded after idle timeout."""
        manager._semantic_engine = mock_semantic_engine
        manager._semantic_last_access = time.time() - 600  # 10 min idle
        manager._idle_timeout_s = 300  # 5 min timeout

        manager._check_idle_unload()
        mock_semantic_engine.unload_model.assert_called_once()
        assert manager._stats["auto_unloads"] == 1

    def test_check_idle_unload_skips_recently_used(self, manager, mock_semantic_engine):
        """Recently used semantic engine should NOT be unloaded."""
        manager._semantic_engine = mock_semantic_engine
        manager._semantic_last_access = time.time()  # Just used
        manager._idle_timeout_s = 300

        manager._check_idle_unload()
        mock_semantic_engine.unload_model.assert_not_called()

    def test_start_stop_auto_unload_monitor(self, manager):
        """Auto-unload monitor should start and stop cleanly."""
        manager.start_auto_unload_monitor()
        assert manager._monitor_thread is not None
        assert manager._monitor_thread.is_alive()

        manager.stop_auto_unload_monitor()
        manager._monitor_thread.join(timeout=3)
        assert not manager._monitor_thread.is_alive()


# ============================================================
#  MODEL SWAP & RAM BUDGET TESTS
# ============================================================

class TestModelSwap:
    """Tests for model swapping and RAM budget enforcement."""

    def test_ram_budget_check_passes(self, manager):
        """_check_ram_budget returns True when budget is available."""
        with patch.object(ModelManager, "_get_current_ram_mb", return_value=100.0):
            manager._ram_budget_mb = 768
            assert manager._check_ram_budget(150) is True  # 100 + 150 = 250 <= 768

    def test_ram_budget_check_fails(self, manager):
        """_check_ram_budget returns False when budget would be exceeded."""
        with patch.object(ModelManager, "_get_current_ram_mb", return_value=700.0):
            manager._ram_budget_mb = 768
            assert manager._check_ram_budget(150) is False  # 700 + 150 = 850 > 768

    def test_try_free_ram_unloads_most_idle(self, manager, mock_semantic_engine, mock_ai_engine):
        """_try_free_ram should unload the most idle model."""
        manager._semantic_engine = mock_semantic_engine
        manager._mini_ai_engine = mock_ai_engine
        manager._semantic_last_access = time.time() - 100  # Semantic older
        manager._ai_last_access = time.time()

        with patch("gc.collect"):
            manager._try_free_ram(needed_mb=400)

        # Semantic is more idle, should be unloaded first
        mock_semantic_engine.unload_model.assert_called()

    def test_ram_pressure_unloads_least_recently_used(self, manager, mock_semantic_engine, mock_ai_engine):
        """RAM pressure should unload the least recently used model."""
        manager._semantic_engine = mock_semantic_engine
        manager._mini_ai_engine = mock_ai_engine
        manager._semantic_last_access = time.time() - 50
        manager._ai_last_access = time.time()
        manager._ram_budget_mb = 768

        with patch.object(ModelManager, "_get_current_ram_mb", return_value=720.0):
            manager._check_ram_pressure()

        # Semantic is less recently used, should be unloaded
        mock_semantic_engine.unload_model.assert_called()
        assert manager._stats["ram_budget_exceeded"] == 1


# ============================================================
#  STATS & STATUS TESTS
# ============================================================

class TestStatsAndStatus:
    """Tests for stats and status reporting."""

    def test_stats_structure(self, manager):
        """Stats dict should contain expected keys."""
        stats = manager.stats
        assert "semantic_loads" in stats
        assert "semantic_unloads" in stats
        assert "ai_loads" in stats
        assert "ai_unloads" in stats
        assert "auto_unloads" in stats
        assert "ram_budget_exceeded" in stats
        assert "lazy_load_enabled" in stats
        assert "semantic_loaded" in stats
        assert "ai_loaded" in stats

    def test_get_status_structure(self, manager):
        """get_status() should return a well-formed status dict."""
        with patch.object(ModelManager, "_get_current_ram_mb", return_value=50.0):
            status = manager.get_status()
            assert status["model_manager"] == "active"
            assert "mode" in status
            assert "models" in status
            assert "semantic_engine" in status["models"]
            assert "mini_ai_engine" in status["models"]

    def test_status_mode_lazy(self, manager):
        """Status mode should be 'lazy' when lazy_load is True."""
        with patch.object(ModelManager, "_get_current_ram_mb", return_value=50.0):
            status = manager.get_status()
            assert status["mode"] == "lazy"


# ============================================================
#  SINGLETON TESTS
# ============================================================

class TestSingleton:
    """Tests for global singleton management."""

    def test_get_model_manager_returns_instance(self):
        """get_model_manager should return a ModelManager instance."""
        mgr = get_model_manager()
        assert isinstance(mgr, ModelManager)

    def test_get_model_manager_returns_same_instance(self):
        """Repeated calls should return the same singleton."""
        mgr1 = get_model_manager()
        mgr2 = get_model_manager()
        assert mgr1 is mgr2

    def test_init_model_manager_creates_new_instance(self):
        """init_model_manager should create a new instance with custom config."""
        with patch.object(ModelManager, "start_auto_unload_monitor"):
            mgr = init_model_manager(lazy_load=False, idle_timeout_s=600, ram_budget_mb=512)
            assert isinstance(mgr, ModelManager)
            assert mgr._idle_timeout_s == 600
            assert mgr._ram_budget_mb == 512
