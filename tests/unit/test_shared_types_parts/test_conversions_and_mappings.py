"""
Tests for shared type conversion functions and mapping dictionaries.
"""

import pytest

from src.core.shared.types import (
    criticality_to_int, criticality_to_path, criticality_to_str,
    CRITICALITY_INT_TO_STR, CRITICALITY_STR_TO_INT,
    CRITICALITY_INT_TO_PATH, CRITICALITY_PATH_TO_INT,
)


# ===========================================================================
#  Test: criticality_to_int conversion
# ===========================================================================

class TestCriticalityToInt:
    """Tests for criticality_to_int conversion function."""

    def test_int_passthrough(self):
        """Integer values should be clamped to 1-3 range."""
        assert criticality_to_int(1) == 1
        assert criticality_to_int(2) == 2
        assert criticality_to_int(3) == 3

    def test_int_clamping_low(self):
        """Values below 1 should be clamped to 1."""
        assert criticality_to_int(0) == 1
        assert criticality_to_int(-5) == 1

    def test_int_clamping_high(self):
        """Values above 3 should be clamped to 3."""
        assert criticality_to_int(10) == 3
        assert criticality_to_int(100) == 3

    def test_str_standard(self):
        assert criticality_to_int("standard") == 1

    def test_str_moderate(self):
        assert criticality_to_int("moderate") == 2

    def test_str_critical(self):
        assert criticality_to_int("critical") == 3

    def test_path_str_low_crit(self):
        assert criticality_to_int("low_crit") == 1

    def test_path_str_standard(self):
        assert criticality_to_int("standard") == 1

    def test_path_str_high_crit(self):
        assert criticality_to_int("high_crit") == 3

    def test_unknown_defaults_to_2(self):
        """Unknown values should default to DEEP_MODERATE (2)."""
        assert criticality_to_int("unknown_value") == 2
        assert criticality_to_int(None) == 2
        assert criticality_to_int(3.14) == 2


# ===========================================================================
#  Test: criticality_to_path conversion
# ===========================================================================

class TestCriticalityToPath:
    """Tests for criticality_to_path conversion function."""

    def test_int_1_to_low_crit(self):
        assert criticality_to_path(1) == "low_crit"

    def test_int_2_to_standard(self):
        assert criticality_to_path(2) == "standard"

    def test_int_3_to_high_crit(self):
        assert criticality_to_path(3) == "high_crit"

    def test_str_to_path(self):
        assert criticality_to_path("critical") == "high_crit"
        assert criticality_to_path("standard") == "low_crit"

    def test_unknown_defaults_to_standard(self):
        assert criticality_to_path("unknown") == "standard"


# ===========================================================================
#  Test: criticality_to_str conversion
# ===========================================================================

class TestCriticalityToStr:
    """Tests for criticality_to_str conversion function."""

    def test_int_1_to_standard(self):
        assert criticality_to_str(1) == "standard"

    def test_int_2_to_moderate(self):
        assert criticality_to_str(2) == "moderate"

    def test_int_3_to_critical(self):
        assert criticality_to_str(3) == "critical"

    def test_path_to_str(self):
        assert criticality_to_str("high_crit") == "critical"

    def test_unknown_defaults_to_moderate(self):
        assert criticality_to_str("unknown") == "moderate"


# ===========================================================================
#  Test: CRITICALITY mapping dictionaries
# ===========================================================================

class TestCriticalityMappings:
    """Tests for CRITICALITY_* mapping dictionaries."""

    def test_int_to_str_completeness(self):
        assert CRITICALITY_INT_TO_STR == {1: "standard", 2: "moderate", 3: "critical"}

    def test_str_to_int_is_inverse(self):
        """CRITICALITY_STR_TO_INT should be the inverse of INT_TO_STR."""
        for k, v in CRITICALITY_INT_TO_STR.items():
            assert CRITICALITY_STR_TO_INT[v] == k

    def test_int_to_path_completeness(self):
        assert CRITICALITY_INT_TO_PATH == {1: "low_crit", 2: "standard", 3: "high_crit"}

    def test_path_to_int_is_inverse(self):
        """CRITICALITY_PATH_TO_INT should be the inverse of INT_TO_PATH."""
        for k, v in CRITICALITY_INT_TO_PATH.items():
            assert CRITICALITY_PATH_TO_INT[v] == k

    def test_all_mappings_have_3_entries(self):
        """All mappings should have exactly 3 entries."""
        assert len(CRITICALITY_INT_TO_STR) == 3
        assert len(CRITICALITY_STR_TO_INT) == 3
        assert len(CRITICALITY_INT_TO_PATH) == 3
        assert len(CRITICALITY_PATH_TO_INT) == 3


# ===========================================================================
#  Test: __all__ completeness
# ===========================================================================

class TestAllCompleteness:
    """Tests that __all__ covers all public names."""

    def test_all_names_importable(self):
        """Every name in __all__ should be accessible."""
        from src.core.shared import types as types_mod
        for name in types_mod.__all__:
            assert hasattr(types_mod, name), f"{name} not accessible in types"

    def test_all_covers_core_classes(self):
        """__all__ should include all core classes."""
        from src.core.shared.types import __all__ as all_names
        expected = {"OperationType", "GoalType", "CriticalityLevel", "RoutePath",
                    "IntentPayload", "RoutingPayload", "PlanStep", "ExecutionPlan",
                    "SandboxResult", "MerkleNode", "ChatMessage", "ChatRequest"}
        assert expected.issubset(set(all_names)), f"Missing: {expected - set(all_names)}"

    def test_all_covers_conversion_utils(self):
        """__all__ should include conversion functions and mappings."""
        from src.core.shared.types import __all__ as all_names
        expected = {"criticality_to_int", "criticality_to_path", "criticality_to_str",
                    "CRITICALITY_INT_TO_STR", "CRITICALITY_STR_TO_INT",
                    "CRITICALITY_INT_TO_PATH", "CRITICALITY_PATH_TO_INT"}
        assert expected.issubset(set(all_names)), f"Missing: {expected - set(all_names)}"
