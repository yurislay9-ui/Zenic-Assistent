"""Tests for request lifecycle, RAM/memory, status, singleton, GC, and process priority."""

import gc
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


# ============================================================
#  Request Lifecycle Tests
# ============================================================

class TestRequestLifecycle:
    """Tests for pre_request and post_request."""

    def test_pre_request_increments_count(self):
        """pre_request should increment request counters."""
        gov = ResourceGovernor()
        initial_count = gov._request_count
        gov.pre_request()
        assert gov._request_count == initial_count + 1
        assert gov.stats["requests_served"] == initial_count + 1

    def test_post_request_runs(self):
        """post_request should run without error."""
        gov = ResourceGovernor()
        gov.post_request()

    def test_multiple_requests(self):
        """Multiple requests should increment counter."""
        gov = ResourceGovernor()
        for _ in range(5):
            gov.pre_request()
        assert gov._request_count == 5


# ============================================================
#  RAM and Memory Tests
# ============================================================

class TestRAMAndMemory:
    """Tests for RAM-related methods."""

    def test_get_z3_memory_limit_normal(self):
        """Should return a reasonable Z3 memory limit."""
        gov = ResourceGovernor(ram_limit_mb=2048)
        gov._ram_usage_mb = 500
        limit = gov.get_z3_memory_limit_mb()
        assert 128 <= limit <= 512

    def test_get_z3_memory_limit_low_ram(self):
        """Should return minimum 128MB when RAM is very low."""
        gov = ResourceGovernor(ram_limit_mb=2048)
        gov._ram_usage_mb = 2000
        limit = gov.get_z3_memory_limit_mb()
        assert limit >= 128

    def test_is_ram_critical_normal(self):
        """Should return False when RAM is not critical."""
        gov = ResourceGovernor(ram_limit_mb=2048)
        gov._ram_usage_mb = 500
        assert gov.is_ram_critical() is False

    def test_is_ram_critical_high(self):
        """Should return True when RAM exceeds 95% limit."""
        gov = ResourceGovernor(ram_limit_mb=2048)
        gov._ram_usage_mb = 2000
        assert gov.is_ram_critical() is True

    def test_is_ram_critical_boundary(self):
        """Should correctly handle boundary at 95%."""
        gov = ResourceGovernor(ram_limit_mb=1000)
        gov._ram_usage_mb = 949
        assert gov.is_ram_critical() is False
        gov._ram_usage_mb = 960
        assert gov.is_ram_critical() is True


# ============================================================
#  Status Reporting Tests
# ============================================================

class TestStatusReporting:
    """Tests for get_status method."""

    def test_status_returns_dict(self):
        """get_status should return a dictionary."""
        gov = ResourceGovernor()
        status = gov.get_status()
        assert isinstance(status, dict)

    def test_status_fields(self):
        """get_status should include all expected fields."""
        gov = ResourceGovernor()
        status = gov.get_status()
        assert "cpu_usage_pct" in status
        assert "ram_usage_mb" in status
        assert "ram_limit_mb" in status
        assert "thermal_throttle" in status
        assert "adaptive_mcts_sims" in status
        assert "adaptive_solver_timeout_ms" in status
        assert "z3_memory_limit_mb" in status
        assert "stats" in status

    def test_status_cpu_usage_percentage(self):
        """cpu_usage_pct should be a percentage (0-100)."""
        gov = ResourceGovernor()
        status = gov.get_status()
        assert 0 <= status["cpu_usage_pct"] <= 100

    def test_status_thermal_throttle_range(self):
        """thermal_throttle should be between 0 and 1."""
        gov = ResourceGovernor()
        status = gov.get_status()
        assert 0 < status["thermal_throttle"] <= 1.0


# ============================================================
#  Singleton Tests
# ============================================================

class TestSingleton:
    """Tests for get_governor and init_governor."""

    def test_get_governor_returns_instance(self):
        """get_governor should return a ResourceGovernor instance."""
        import src.core.shared.resource_governor as rg_module
        gov = get_governor()
        assert isinstance(gov, ResourceGovernor)

    def test_get_governor_singleton(self):
        """get_governor should return the same instance on repeated calls."""
        import src.core.shared.resource_governor as rg_module
        gov1 = get_governor()
        gov2 = get_governor()
        assert gov1 is gov2

    def test_init_governor_with_config(self):
        """init_governor should create a governor with custom config."""
        import src.core.shared.resource_governor as rg_module
        gov = init_governor(ram_limit_mb=1024)
        assert isinstance(gov, ResourceGovernor)
        assert gov.ram_limit_mb == 1024
        gov.stop_monitoring()

    def test_init_governor_starts_monitoring(self):
        """init_governor should start monitoring."""
        import src.core.shared.resource_governor as rg_module
        gov = init_governor()
        assert gov._monitor_thread is not None
        assert gov._monitor_thread.is_alive()
        gov.stop_monitoring()


# ============================================================
#  GC Tuning Tests
# ============================================================

class TestGCTuning:
    """Tests for tune_gc_for_arm function."""

    def test_tune_gc_for_arm_sets_thresholds(self):
        """tune_gc_for_arm should set GC thresholds for ARM."""
        original = gc.get_threshold()
        try:
            tune_gc_for_arm()
            new_thresholds = gc.get_threshold()
            assert new_thresholds == (1000, 15, 15)
        finally:
            gc.set_threshold(*original)

    def test_tune_gc_idempotent(self):
        """Calling tune_gc_for_arm twice should not change thresholds."""
        original = gc.get_threshold()
        try:
            tune_gc_for_arm()
            tune_gc_for_arm()
            assert gc.get_threshold() == (1000, 15, 15)
        finally:
            gc.set_threshold(*original)


# ============================================================
#  Process Priority Tests
# ============================================================

class TestProcessPriority:
    """Tests for set_process_priority_low function."""

    def test_set_process_priority_low_no_crash(self):
        """set_process_priority_low should not crash (may fail gracefully)."""
        try:
            set_process_priority_low()
        except (PermissionError, AttributeError):
            pass
