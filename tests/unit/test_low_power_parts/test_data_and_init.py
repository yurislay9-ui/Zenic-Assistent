"""
Tests for HardwareState dataclass, PowerMode enum, initialization, and force mode.
"""

import pytest

from src.core.low_power_sequential import (
    LowPowerSequentialMode, PowerMode, HardwareState,
)


# ============================================================
#  HardwareState Tests
# ============================================================

class TestHardwareState:
    """Tests for HardwareState dataclass."""

    def test_defaults(self):
        """Should have sensible defaults."""
        hw = HardwareState()
        assert hw.cpu_usage == 0.0
        assert hw.battery_level == 100.0
        assert hw.battery_charging is True
        assert hw.temperature_c == 45.0
        assert hw.thermal_throttle == 1.0

    def test_ram_pct_calculation(self):
        """Should calculate RAM percentage correctly."""
        hw = HardwareState(ram_usage_mb=1024.0, ram_limit_mb=2048.0)
        assert hw.ram_pct == 50.0

    def test_ram_pct_zero_limit(self):
        """Should handle zero RAM limit gracefully."""
        hw = HardwareState(ram_usage_mb=500.0, ram_limit_mb=0.0)
        assert hw.ram_pct == 0.0


# ============================================================
#  PowerMode Tests
# ============================================================

class TestPowerMode:
    """Tests for PowerMode enum."""

    def test_mode_values(self):
        """Should have three modes with correct values."""
        assert PowerMode.NORMAL.value == "normal"
        assert PowerMode.CONSERVATIVE.value == "conservative"
        assert PowerMode.EMERGENCY.value == "emergency"

    def test_mode_rank(self):
        """Should rank modes by severity."""
        assert LowPowerSequentialMode._mode_rank(PowerMode.NORMAL) == 0
        assert LowPowerSequentialMode._mode_rank(PowerMode.CONSERVATIVE) == 1
        assert LowPowerSequentialMode._mode_rank(PowerMode.EMERGENCY) == 2

    def test_mode_rank_unknown(self):
        """Unknown mode should default to rank 0."""
        assert LowPowerSequentialMode._mode_rank(None) == 0


# ============================================================
#  Initialization Tests
# ============================================================

class TestInitialization:
    """Tests for LowPowerSequentialMode initialization."""

    def test_default_mode_is_normal(self, lps):
        """Should start in NORMAL mode."""
        assert lps._current_mode == PowerMode.NORMAL

    def test_no_forced_mode(self, lps):
        """Should have no forced mode by default."""
        assert lps._forced_mode is None

    def test_empty_history(self, lps):
        """Should start with empty history."""
        assert len(lps._history) == 0


# ============================================================
#  Force Mode Tests
# ============================================================

class TestForceMode:
    """Tests for forced mode override."""

    def test_force_conservative(self, lps):
        """Should force CONSERVATIVE mode."""
        lps.force_mode(PowerMode.CONSERVATIVE)
        assert lps._forced_mode == PowerMode.CONSERVATIVE
        mode = lps.evaluate()
        assert mode == PowerMode.CONSERVATIVE

    def test_force_emergency(self, lps):
        """Should force EMERGENCY mode."""
        lps.force_mode(PowerMode.EMERGENCY)
        mode = lps.evaluate()
        assert mode == PowerMode.EMERGENCY

    def test_force_none_clears(self, lps):
        """Should clear forced mode when set to None."""
        lps.force_mode(PowerMode.EMERGENCY)
        lps.force_mode(None)
        assert lps._forced_mode is None

    def test_forced_mode_overrides_hardware(self, lps):
        """Forced mode should override hardware evaluation."""
        lps.force_mode(PowerMode.EMERGENCY)
        # Even with normal hardware reads, should stay EMERGENCY
        mode = lps.evaluate()
        assert mode == PowerMode.EMERGENCY
