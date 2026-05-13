"""
Unit tests for LowPowerSequentialMode

Tests mode activation (NORMAL, CONSERVATIVE, EMERGENCY),
sequential execution decisions, MCTS/solver scaling,
agent filtering, and hardware state evaluation.
"""

import pytest
from unittest.mock import MagicMock

from src.core.low_power_sequential import (
    LowPowerSequentialMode, PowerMode, HardwareState,
)


# ============================================================
#  Fixtures (shared with sub-modules)
# ============================================================

@pytest.fixture
def lps():
    """Create a LowPowerSequentialMode without governor."""
    return LowPowerSequentialMode(governor=None)


@pytest.fixture
def lps_with_governor():
    """Create a LowPowerSequentialMode with a mocked governor."""
    gov = MagicMock()
    gov._cpu_usage = 0.3
    gov._ram_usage_mb = 500.0
    gov.ram_limit_mb = 2048.0
    gov._thermal_throttle = 1.0
    return LowPowerSequentialMode(governor=gov)


from .test_low_power_parts import *  # noqa: F401,F403
