"""
Tests for active agents, execution order, stats, governor integration, and current_mode property.
"""

import pytest
from unittest.mock import MagicMock

from src.core.low_power_sequential import (
    LowPowerSequentialMode, PowerMode, HardwareState,
)


# ============================================================
#  Active Agents Tests
# ============================================================

class TestActiveAgents:
    """Tests for get_active_agents method."""

    def test_normal_all_agents(self, lps):
        """NORMAL mode should include all agents."""
        lps.force_mode(PowerMode.NORMAL)
        agents = lps.get_active_agents()
        assert "INTENT" in agents
        assert "ARCHITECT" in agents
        assert "RISK" in agents
        assert "WRITER" in agents

    def test_conservative_skips_risk(self, lps):
        """CONSERVATIVE mode should skip RISK agent."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        agents = lps.get_active_agents()
        assert "RISK" not in agents
        assert "INTENT" in agents

    def test_emergency_critical_only(self, lps):
        """EMERGENCY mode should only include critical agents."""
        lps.force_mode(PowerMode.EMERGENCY)
        agents = lps.get_active_agents()
        assert "INTENT" in agents
        assert "EXTRACTOR" in agents
        assert "WRITER" in agents
        assert "FORMATTER" in agents
        assert "ARCHITECT" not in agents
        assert "PLANNER" not in agents
        assert "RISK" not in agents


# ============================================================
#  Execution Order Tests
# ============================================================

class TestExecutionOrder:
    """Tests for get_execution_order method."""

    def test_normal_returns_parallel(self, lps):
        """NORMAL mode should return parallel execution."""
        lps.force_mode(PowerMode.NORMAL)
        order = lps.get_execution_order(layer=4)
        assert order == ["parallel"]

    def test_conservative_layer4(self, lps):
        """CONSERVATIVE mode layer 4 should return ARCHITECT then PLANNER."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        order = lps.get_execution_order(layer=4)
        assert order == ["ARCHITECT", "PLANNER"]

    def test_emergency_layer4(self, lps):
        """EMERGENCY mode layer 4 should return only ARCHITECT."""
        lps.force_mode(PowerMode.EMERGENCY)
        order = lps.get_execution_order(layer=4)
        assert order == ["ARCHITECT"]


# ============================================================
#  Stats Tests
# ============================================================

class TestLPSStats:
    """Tests for stats property."""

    def test_stats_structure(self, lps):
        """Stats should contain expected keys."""
        lps.force_mode(PowerMode.NORMAL)
        stats = lps.stats
        assert "current_mode" in stats
        assert "cpu_usage" in stats
        assert "ram_pct" in stats
        assert "temperature_c" in stats
        assert "battery_level" in stats
        assert "parallel_layer4" in stats
        assert "parallel_agents" in stats
        assert "mcts_scale" in stats
        assert "active_agents" in stats

    def test_stats_forced_mode(self, lps):
        """Stats should reflect forced mode."""
        lps.force_mode(PowerMode.EMERGENCY)
        stats = lps.stats
        assert stats["current_mode"] == "emergency"
        assert stats["forced_mode"] == "emergency"

    def test_stats_no_forced_mode(self, lps):
        """Stats should show None for forced_mode when not forced."""
        stats = lps.stats
        assert stats["forced_mode"] is None


# ============================================================
#  Governor Integration Tests
# ============================================================

class TestGovernorIntegration:
    """Tests for governor-based hardware state reading."""

    def test_set_governor(self, lps):
        """Should accept a governor reference."""
        gov = MagicMock()
        lps.set_governor(gov)
        assert lps._governor is gov

    def test_read_hardware_from_governor(self, lps_with_governor):
        """Should read CPU/RAM stats from governor."""
        hw = lps_with_governor._read_hardware_state()
        assert hw.cpu_usage == 0.3
        assert hw.ram_usage_mb == 500.0

    def test_read_temperature_fallback(self, lps):
        """Should return safe default temperature without governor."""
        hw = lps._read_hardware_state()
        assert hw.temperature_c == 45.0

    def test_read_battery_fallback(self, lps):
        """Should return safe default battery level without real battery."""
        hw = lps._read_hardware_state()
        assert hw.battery_level == 100.0
        assert hw.battery_charging is True


# ============================================================
#  current_mode Property Tests
# ============================================================

class TestCurrentModeProperty:
    """Tests for current_mode property (no re-evaluation)."""

    def test_returns_current_mode(self, lps):
        """Should return the current mode without re-evaluating."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        assert lps.current_mode == PowerMode.CONSERVATIVE

    def test_does_not_re_evaluate(self, lps):
        """Should return cached mode, not trigger hardware read."""
        lps.force_mode(PowerMode.EMERGENCY)
        # Clear force, but current_mode should still be EMERGENCY
        lps._forced_mode = None
        # current_mode property doesn't re-evaluate
        assert lps.current_mode == PowerMode.EMERGENCY

    def test_initial_mode_is_normal(self, lps):
        """Should start as NORMAL before any evaluate call."""
        assert lps.current_mode == PowerMode.NORMAL
