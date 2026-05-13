"""Tests for constructor, monitoring, CPU throttle, and adaptive budgets."""

import gc
import time
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.shared.resource_governor import (
    ResourceGovernor,
    get_governor,
    init_governor,
    tune_gc_for_arm,
    set_process_priority_low,
)


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch):
    """Reset ResourceGovernor singleton for each test."""
    try:
        import src.core.shared.resource_governor as rg_module
        monkeypatch.setattr(rg_module, '_governor', None, raising=False)
    except ImportError:
        pass


# ============================================================
#  Constructor Tests
# ============================================================

class TestResourceGovernorConstructor:
    """Tests for ResourceGovernor initialization."""

    def test_default_parameters(self):
        """Should use default RAM limit and GC threshold."""
        gov = ResourceGovernor()
        assert gov.ram_limit_mb == ResourceGovernor.DEFAULT_RAM_LIMIT_MB
        assert gov.gc_threshold_mb == ResourceGovernor.DEFAULT_GC_THRESHOLD_MB

    def test_custom_ram_limit(self):
        """Should accept custom RAM limit."""
        gov = ResourceGovernor(ram_limit_mb=1024)
        assert gov.ram_limit_mb == 1024

    def test_custom_gc_threshold(self):
        """Should accept custom GC threshold."""
        gov = ResourceGovernor(gc_threshold_mb=768)
        assert gov.gc_threshold_mb == 768

    def test_default_cpu_sleep(self):
        """Should have DEFAULT_CPU_SLEEP_MS constant."""
        assert ResourceGovernor.DEFAULT_CPU_SLEEP_MS == 50

    def test_initial_state(self):
        """Should initialize monitoring state correctly."""
        gov = ResourceGovernor()
        assert gov._cpu_usage == 0.0
        assert gov._ram_usage_mb == 0.0
        assert gov._thermal_throttle == 1.0
        assert gov._gc_count == 0
        assert gov._request_count == 0

    def test_stats_initialized(self):
        """Should initialize stats dict."""
        gov = ResourceGovernor()
        assert "gc_forced" in gov.stats
        assert "thermal_throttles" in gov.stats
        assert "ram_peaks" in gov.stats
        assert "requests_served" in gov.stats

    def test_default_constants(self):
        """Should have sensible default constants."""
        assert ResourceGovernor.DEFAULT_RAM_LIMIT_MB == 2048
        assert ResourceGovernor.DEFAULT_GC_THRESHOLD_MB == 1536
        assert ResourceGovernor.THERMAL_SCALE_BACK_THRESHOLD == 30


# ============================================================
#  Monitoring Tests
# ============================================================

class TestMonitoring:
    """Tests for start/stop monitoring."""

    def test_start_monitoring(self):
        """Should start the monitoring thread."""
        gov = ResourceGovernor()
        gov.start_monitoring()
        try:
            assert gov._monitor_thread is not None
            assert gov._monitor_thread.is_alive()
        finally:
            gov.stop_monitoring()

    def test_stop_monitoring(self):
        """Should stop the monitoring thread."""
        gov = ResourceGovernor()
        gov.start_monitoring()
        gov.stop_monitoring()
        assert gov._stop_event.is_set()

    def test_double_start(self):
        """Should not create duplicate threads on double start."""
        gov = ResourceGovernor()
        gov.start_monitoring()
        try:
            thread1 = gov._monitor_thread
            gov.start_monitoring()
            thread2 = gov._monitor_thread
            assert thread1 is thread2
        finally:
            gov.stop_monitoring()

    def test_monitoring_is_daemon(self):
        """Monitoring thread should be a daemon thread."""
        gov = ResourceGovernor()
        gov.start_monitoring()
        try:
            assert gov._monitor_thread.daemon is True
        finally:
            gov.stop_monitoring()


# ============================================================
#  CPU Throttle Tests
# ============================================================

class TestCPUThrottle:
    """Tests for cpu_throttle_sleep."""

    def test_throttle_sleep_returns(self):
        """cpu_throttle_sleep should return (not hang)."""
        gov = ResourceGovernor()
        start = time.time()
        gov.cpu_throttle_sleep()
        elapsed = time.time() - start
        assert elapsed >= 0.04

    def test_throttle_with_low_cpu(self):
        """Low CPU should result in default sleep."""
        gov = ResourceGovernor()
        gov._cpu_usage = 0.2
        start = time.time()
        gov.cpu_throttle_sleep()
        elapsed = time.time() - start
        assert elapsed >= 0.04

    def test_throttle_with_high_cpu(self):
        """High CPU should result in longer sleep."""
        gov = ResourceGovernor()
        gov._cpu_usage = 0.9
        start = time.time()
        gov.cpu_throttle_sleep()
        elapsed = time.time() - start
        assert elapsed >= 0.1

    def test_throttle_with_thermal(self):
        """Thermal throttle should affect sleep duration."""
        gov = ResourceGovernor()
        gov._cpu_usage = 0.2
        gov._thermal_throttle = 0.5
        start = time.time()
        gov.cpu_throttle_sleep()
        elapsed = time.time() - start
        assert elapsed >= 0.04


# ============================================================
#  Adaptive Budget Tests
# ============================================================

class TestAdaptiveBudgets:
    """Tests for adaptive MCTS simulations and solver timeout."""

    def test_adaptive_mcts_full_sims(self):
        """Low CPU should allow full MCTS simulations."""
        gov = ResourceGovernor()
        gov._cpu_usage = 0.1
        gov._thermal_throttle = 1.0
        sims = gov.get_adaptive_mcts_simulations(base_simulations=100)
        assert sims == 100

    def test_adaptive_mcts_reduced_sims(self):
        """High CPU should reduce MCTS simulations."""
        gov = ResourceGovernor()
        gov._cpu_usage = 0.9
        gov._thermal_throttle = 1.0
        sims = gov.get_adaptive_mcts_simulations(base_simulations=100)
        assert sims < 100
        assert sims >= 10

    def test_adaptive_mcts_thermal_reduction(self):
        """Thermal throttle should further reduce MCTS simulations."""
        gov = ResourceGovernor()
        gov._cpu_usage = 0.1
        gov._thermal_throttle = 0.5
        sims = gov.get_adaptive_mcts_simulations(base_simulations=100)
        assert sims == 50

    def test_adaptive_mcts_minimum(self):
        """MCTS simulations should never go below 10."""
        gov = ResourceGovernor()
        gov._cpu_usage = 1.0
        gov._thermal_throttle = 0.1
        sims = gov.get_adaptive_mcts_simulations(base_simulations=100)
        assert sims >= 10

    def test_adaptive_solver_timeout_full(self):
        """Low resource usage should allow full solver timeout."""
        gov = ResourceGovernor()
        gov._cpu_usage = 0.1
        gov._ram_usage_mb = 100
        gov._thermal_throttle = 1.0
        timeout = gov.get_adaptive_solver_timeout(base_timeout_ms=15000)
        assert timeout == 15000

    def test_adaptive_solver_timeout_reduced_ram(self):
        """High RAM usage should reduce solver timeout."""
        gov = ResourceGovernor()
        gov._ram_usage_mb = 1900
        gov._thermal_throttle = 1.0
        timeout = gov.get_adaptive_solver_timeout(base_timeout_ms=15000)
        assert timeout < 15000

    def test_adaptive_solver_timeout_thermal(self):
        """Thermal throttle should reduce solver timeout."""
        gov = ResourceGovernor()
        gov._ram_usage_mb = 0
        gov._thermal_throttle = 0.5
        timeout = gov.get_adaptive_solver_timeout(base_timeout_ms=15000)
        assert timeout == 7500

    def test_adaptive_solver_timeout_minimum(self):
        """Solver timeout should never go below 3000ms."""
        gov = ResourceGovernor()
        gov._ram_usage_mb = 3000
        gov._thermal_throttle = 0.01
        timeout = gov.get_adaptive_solver_timeout(base_timeout_ms=15000)
        assert timeout >= 3000
