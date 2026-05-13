"""
Tests for shared type constants: OperationType, GoalType, CriticalityLevel, RoutePath.
"""

import pytest

from src.core.shared.types import (
    OperationType, GoalType, CriticalityLevel, RoutePath,
)


# ===========================================================================
#  Test: OperationType
# ===========================================================================

class TestOperationType:
    """Tests for OperationType constants."""

    def test_create_constant(self):
        assert OperationType.CREATE == "CREATE"

    def test_refactor_constant(self):
        assert OperationType.REFACTOR == "REFACTOR"

    def test_delete_constant(self):
        assert OperationType.DELETE == "DELETE"

    def test_search_constant(self):
        assert OperationType.SEARCH == "SEARCH"

    def test_analyze_constant(self):
        assert OperationType.ANALYZE == "ANALYZE"

    def test_explain_constant(self):
        assert OperationType.EXPLAIN == "EXPLAIN"

    def test_debug_constant(self):
        assert OperationType.DEBUG == "DEBUG"

    def test_optimize_constant(self):
        assert OperationType.OPTIMIZE == "OPTIMIZE"

    def test_all_operations_are_strings(self):
        """All operation constants should be strings."""
        ops = [OperationType.CREATE, OperationType.REFACTOR, OperationType.DELETE,
               OperationType.SEARCH, OperationType.ANALYZE, OperationType.EXPLAIN,
               OperationType.DEBUG, OperationType.OPTIMIZE]
        assert all(isinstance(op, str) for op in ops)


# ===========================================================================
#  Test: GoalType
# ===========================================================================

class TestGoalType:
    """Tests for GoalType constants."""

    def test_complexity_reduction(self):
        assert GoalType.COMPLEXITY_REDUCTION == "COMPLEXITY_REDUCTION"

    def test_modern_pattern(self):
        assert GoalType.MODERN_PATTERN == "MODERN_PATTERN"

    def test_bug_fix(self):
        assert GoalType.BUG_FIX == "BUG_FIX"

    def test_feature_add(self):
        assert GoalType.FEATURE_ADD == "FEATURE_ADD"

    def test_security_harden(self):
        assert GoalType.SECURITY_HARDEN == "SECURITY_HARDEN"

    def test_performance(self):
        assert GoalType.PERFORMANCE == "PERFORMANCE"

    def test_readability(self):
        assert GoalType.READABILITY == "READABILITY"


# ===========================================================================
#  Test: CriticalityLevel
# ===========================================================================

class TestCriticalityLevel:
    """Tests for CriticalityLevel constants."""

    def test_fast_standard_is_1(self):
        assert CriticalityLevel.FAST_STANDARD == 1

    def test_deep_moderate_is_2(self):
        assert CriticalityLevel.DEEP_MODERATE == 2

    def test_surgical_critical_is_3(self):
        assert CriticalityLevel.SURGICAL_CRITICAL == 3

    def test_levels_are_ordered(self):
        """Criticality levels should be ordered 1 < 2 < 3."""
        assert CriticalityLevel.FAST_STANDARD < CriticalityLevel.DEEP_MODERATE
        assert CriticalityLevel.DEEP_MODERATE < CriticalityLevel.SURGICAL_CRITICAL


# ===========================================================================
#  Test: RoutePath
# ===========================================================================

class TestRoutePath:
    """Tests for RoutePath constants."""

    def test_fast_path(self):
        assert RoutePath.FAST_PATH == "FAST_PATH_REGEX"

    def test_deep_path(self):
        assert RoutePath.DEEP_PATH == "DEEP_PATH_CONSTRAINT"

    def test_surgical_path(self):
        assert RoutePath.SURGICAL_PATH == "SURGICAL_PATH_FULL"

    def test_paths_are_strings(self):
        """All route path constants should be strings."""
        paths = [RoutePath.FAST_PATH, RoutePath.DEEP_PATH, RoutePath.SURGICAL_PATH]
        assert all(isinstance(p, str) for p in paths)
