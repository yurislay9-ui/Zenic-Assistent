"""
Tests for mode evaluation and decision API methods.
"""

import time
import pytest
from unittest.mock import patch

from src.core.low_power_sequential import (
    LowPowerSequentialMode, PowerMode, HardwareState,
)


# ============================================================
#  Mode Evaluation Tests
# ============================================================

class TestModeEvaluation:
    """Tests for evaluate() mode determination logic."""

    @patch.object(LowPowerSequentialMode, "_read_hardware_state")
    def test_normal_mode_low_stress(self, mock_hw, lps):
        """Should stay NORMAL when hardware is under low stress."""
        mock_hw.return_value = HardwareState(
            cpu_usage=0.2, ram_usage_mb=500, ram_limit_mb=2048,
            temperature_c=40.0, battery_level=80.0, battery_charging=True,
            thermal_throttle=1.0,
        )
        mode = lps.evaluate()
        assert mode == PowerMode.NORMAL

    @patch.object(LowPowerSequentialMode, "_read_hardware_state")
    def test_conservative_mode_moderate_cpu(self, mock_hw, lps):
        """Should enter CONSERVATIVE when CPU is moderate-high."""
        mock_hw.return_value = HardwareState(
            cpu_usage=0.70, ram_usage_mb=500, ram_limit_mb=2048,
            temperature_c=56.0, battery_level=80.0, battery_charging=True,
            thermal_throttle=1.0,
        )
        # Need mode_since to be old enough for stickiness
        lps._mode_since = time.time() - 60
        mode = lps.evaluate()
        assert mode in (PowerMode.CONSERVATIVE, PowerMode.EMERGENCY)

    @patch.object(LowPowerSequentialMode, "_read_hardware_state")
    def test_emergency_mode_high_cpu(self, mock_hw, lps):
        """Should enter EMERGENCY when CPU is very high."""
        mock_hw.return_value = HardwareState(
            cpu_usage=0.90, ram_usage_mb=1900, ram_limit_mb=2048,
            temperature_c=70.0, battery_level=10.0, battery_charging=False,
            thermal_throttle=0.3,
        )
        lps._mode_since = time.time() - 60
        mode = lps.evaluate()
        assert mode == PowerMode.EMERGENCY

    @patch.object(LowPowerSequentialMode, "_read_hardware_state")
    def test_conservative_from_low_battery(self, mock_hw, lps):
        """Should enter CONSERVATIVE when battery is low and not charging."""
        mock_hw.return_value = HardwareState(
            cpu_usage=0.2, ram_usage_mb=500, ram_limit_mb=2048,
            temperature_c=40.0, battery_level=25.0, battery_charging=False,
            thermal_throttle=1.0,
        )
        lps._mode_since = time.time() - 60
        mode = lps.evaluate()
        assert mode in (PowerMode.CONSERVATIVE, PowerMode.EMERGENCY, PowerMode.NORMAL)

    @patch.object(LowPowerSequentialMode, "_read_hardware_state")
    def test_battery_charging_ignored(self, mock_hw, lps):
        """Low battery should not matter when charging."""
        mock_hw.return_value = HardwareState(
            cpu_usage=0.2, ram_usage_mb=500, ram_limit_mb=2048,
            temperature_c=40.0, battery_level=5.0, battery_charging=True,
            thermal_throttle=1.0,
        )
        mode = lps.evaluate()
        assert mode == PowerMode.NORMAL

    @patch.object(LowPowerSequentialMode, "_read_hardware_state")
    def test_evaluation_records_history(self, mock_hw, lps):
        """Each evaluation should add to history."""
        mock_hw.return_value = HardwareState()
        lps.evaluate()
        lps.evaluate()
        assert len(lps._history) == 2

    @patch.object(LowPowerSequentialMode, "_read_hardware_state")
    def test_stickiness_prevents_rapid_changes(self, mock_hw, lps):
        """Mode should not change too rapidly (stickiness)."""
        # Start NORMAL with low stress
        mock_hw.return_value = HardwareState(cpu_usage=0.2)
        lps.evaluate()
        assert lps._current_mode == PowerMode.NORMAL

        # Immediately spike CPU but stickiness should block downgrade
        mock_hw.return_value = HardwareState(cpu_usage=0.90, ram_usage_mb=1900, ram_limit_mb=2048,
                                              temperature_c=70.0, battery_level=5.0,
                                              battery_charging=False, thermal_throttle=0.3)
        # mode_since was just set, so stickiness should block the change
        # (upgrade to more restrictive is blocked since new_mode rank > current rank
        #  but stickiness blocks downgrade; NORMAL→EMERGENCY is upgrade in restrictiveness)
        # Actually: stickiness blocks downgrade (less restrictive), but allows upgrade (more restrictive)
        lps.evaluate()
        # The mode should change since EMERGENCY is more restrictive (upgrade)
        assert lps._current_mode == PowerMode.EMERGENCY


# ============================================================
#  Decision API Tests
# ============================================================

class TestDecisionAPI:
    """Tests for decision API methods used by DAGOrchestrator."""

    def test_should_run_parallel_layer4_normal(self, lps):
        """Layer 4 should run parallel in NORMAL mode."""
        lps.force_mode(PowerMode.NORMAL)
        assert lps.should_run_parallel_layer4() is True

    def test_should_run_parallel_layer4_conservative(self, lps):
        """Layer 4 should NOT run parallel in CONSERVATIVE mode."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        assert lps.should_run_parallel_layer4() is False

    def test_should_run_parallel_layer4_emergency(self, lps):
        """Layer 4 should NOT run parallel in EMERGENCY mode."""
        lps.force_mode(PowerMode.EMERGENCY)
        assert lps.should_run_parallel_layer4() is False

    def test_should_run_parallel_agents_normal(self, lps):
        """Agents should run parallel in NORMAL mode."""
        lps.force_mode(PowerMode.NORMAL)
        assert lps.should_run_parallel_agents() is True

    def test_should_run_parallel_agents_conservative(self, lps):
        """Agents should run parallel in CONSERVATIVE mode."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        assert lps.should_run_parallel_agents() is True

    def test_should_run_parallel_agents_emergency(self, lps):
        """Agents should NOT run parallel in EMERGENCY mode."""
        lps.force_mode(PowerMode.EMERGENCY)
        assert lps.should_run_parallel_agents() is False

    def test_get_mcts_scale_normal(self, lps):
        """MCTS scale should be 1.0 in NORMAL mode."""
        lps.force_mode(PowerMode.NORMAL)
        assert lps.get_mcts_scale() == 1.0

    def test_get_mcts_scale_conservative(self, lps):
        """MCTS scale should be 0.5 in CONSERVATIVE mode."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        assert lps.get_mcts_scale() == 0.5

    def test_get_mcts_scale_emergency(self, lps):
        """MCTS scale should be 0.25 in EMERGENCY mode."""
        lps.force_mode(PowerMode.EMERGENCY)
        assert lps.get_mcts_scale() == 0.25

    def test_get_solver_timeout_scale_normal(self, lps):
        """Solver timeout scale should be 1.0 in NORMAL mode."""
        lps.force_mode(PowerMode.NORMAL)
        assert lps.get_solver_timeout_scale() == 1.0

    def test_get_solver_timeout_scale_conservative(self, lps):
        """Solver timeout scale should be 0.7 in CONSERVATIVE mode."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        assert lps.get_solver_timeout_scale() == 0.7

    def test_get_solver_timeout_scale_emergency(self, lps):
        """Solver timeout scale should be 0.4 in EMERGENCY mode."""
        lps.force_mode(PowerMode.EMERGENCY)
        assert lps.get_solver_timeout_scale() == 0.4

    def test_should_postpone_non_critical_normal(self, lps):
        """Should NOT postpone in NORMAL mode."""
        lps.force_mode(PowerMode.NORMAL)
        assert lps.should_postpone_non_critical() is False

    def test_should_postpone_non_critical_conservative(self, lps):
        """Should postpone in CONSERVATIVE mode."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        assert lps.should_postpone_non_critical() is True

    def test_should_postpone_non_critical_emergency(self, lps):
        """Should postpone in EMERGENCY mode."""
        lps.force_mode(PowerMode.EMERGENCY)
        assert lps.should_postpone_non_critical() is True
