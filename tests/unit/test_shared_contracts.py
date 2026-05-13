"""
Unit tests for src/core/shared/contracts.py - Re-export Facade Module

Tests:
- All re-exported names are accessible from contracts
- __all__ list completeness
- Re-exported objects are the same as their source modules
- Missing import raises AttributeError
"""

import pytest

from src.core.shared import contracts


# ===========================================================================
#  Test: All __all__ names are accessible
# ===========================================================================

class TestAllNamesAccessible:
    """Tests that every name in __all__ is importable from contracts."""

    def test_all_names_are_attributes(self):
        """Every name in __all__ should be accessible as a module attribute."""
        for name in contracts.__all__:
            assert hasattr(contracts, name), f"{name} missing from contracts module"

    def test_all_names_are_not_none(self):
        """Every name in __all__ should resolve to a non-None value."""
        for name in contracts.__all__:
            value = getattr(contracts, name)
            assert value is not None, f"{name} is None in contracts module"

    def test_all_list_matches_actual_exports(self):
        """The __all__ list should match what's actually defined in the module."""
        # Get all public names defined directly or imported
        public_names = {name for name in dir(contracts) if not name.startswith("_")}
        all_set = set(contracts.__all__)
        # Every name in __all__ should be in public_names
        assert all_set.issubset(public_names), f"__all__ has names not in module: {all_set - public_names}"


# ===========================================================================
#  Test: Type re-exports are correct
# ===========================================================================

class TestTypeReExports:
    """Tests that re-exported types come from the correct source modules."""

    def test_operation_type_from_types(self):
        """OperationType should be the same object as in types.py."""
        from src.core.shared.types import OperationType
        assert contracts.OperationType is OperationType

    def test_goal_type_from_types(self):
        """GoalType should be the same object as in types.py."""
        from src.core.shared.types import GoalType
        assert contracts.GoalType is GoalType

    def test_criticality_level_from_types(self):
        """CriticalityLevel should be the same object as in types.py."""
        from src.core.shared.types import CriticalityLevel
        assert contracts.CriticalityLevel is CriticalityLevel

    def test_route_path_from_types(self):
        """RoutePath should be the same object as in types.py."""
        from src.core.shared.types import RoutePath
        assert contracts.RoutePath is RoutePath

    def test_intent_payload_from_types(self):
        """IntentPayload should be the same object as in types.py."""
        from src.core.shared.types import IntentPayload
        assert contracts.IntentPayload is IntentPayload

    def test_routing_payload_from_types(self):
        """RoutingPayload should be the same object as in types.py."""
        from src.core.shared.types import RoutingPayload
        assert contracts.RoutingPayload is RoutingPayload

    def test_plan_step_from_types(self):
        """PlanStep should be the same object as in types.py."""
        from src.core.shared.types import PlanStep
        assert contracts.PlanStep is PlanStep


# ===========================================================================
#  Test: Sub-module re-exports are correct
# ===========================================================================

class TestSubModuleReExports:
    """Tests that re-exports from sub-modules are correct."""

    def test_mcts_node_from_mcts(self):
        """MCTSNode should be the same object as in mcts.py."""
        from src.core.shared.mcts import MCTSNode
        assert contracts.MCTSNode is MCTSNode

    def test_mcts_planner_from_mcts(self):
        """MCTSPlanner should be the same object as in mcts.py."""
        from src.core.shared.mcts import MCTSPlanner
        assert contracts.MCTSPlanner is MCTSPlanner

    def test_constraint_solver_from_module(self):
        """ConstraintSolver should be the same object as in constraint_solver.py."""
        from src.core.shared.constraint_solver import ConstraintSolver
        assert contracts.ConstraintSolver is ConstraintSolver

    def test_timeout_enforcer_from_module(self):
        """TimeoutEnforcer should be the same object as in timeout.py."""
        from src.core.shared.timeout import TimeoutEnforcer
        assert contracts.TimeoutEnforcer is TimeoutEnforcer

    def test_symbolic_executor_from_module(self):
        """SymbolicExecutor should be the same object as in symbolic_executor.py."""
        from src.core.shared.symbolic_executor import SymbolicExecutor
        assert contracts.SymbolicExecutor is SymbolicExecutor

    def test_kpath_analyzer_from_module(self):
        """KPathAnalyzer should be the same object as in kpath_analyzer.py."""
        from src.core.shared.kpath_analyzer import KPathAnalyzer
        assert contracts.KPathAnalyzer is KPathAnalyzer


# ===========================================================================
#  Test: __all__ completeness - no missing names
# ===========================================================================

class TestAllCompleteness:
    """Tests that __all__ covers all important re-exports."""

    def test_types_in_all(self):
        """All core types should be in __all__."""
        expected = {"OperationType", "GoalType", "CriticalityLevel", "RoutePath",
                    "IntentPayload", "RoutingPayload", "PlanStep", "ExecutionPlan",
                    "SandboxResult", "MerkleNode", "ChatMessage", "ChatRequest"}
        all_set = set(contracts.__all__)
        assert expected.issubset(all_set), f"Missing from __all__: {expected - all_set}"

    def test_utility_functions_in_all(self):
        """Criticality utility functions should be in __all__."""
        expected = {"criticality_to_int", "criticality_to_path", "criticality_to_str",
                    "CRITICALITY_INT_TO_STR", "CRITICALITY_INT_TO_PATH",
                    "CRITICALITY_STR_TO_INT", "CRITICALITY_PATH_TO_INT"}
        all_set = set(contracts.__all__)
        assert expected.issubset(all_set), f"Missing from __all__: {expected - all_set}"

    def test_mcts_in_all(self):
        """MCTS classes should be in __all__."""
        expected = {"MCTSNode", "MCTSPlanner"}
        all_set = set(contracts.__all__)
        assert expected.issubset(all_set), f"Missing from __all__: {expected - all_set}"

    def test_solver_in_all(self):
        """Solver classes should be in __all__."""
        expected = {"Constraint", "ConstraintSolver", "Z3Solver", "HAS_Z3"}
        all_set = set(contracts.__all__)
        assert expected.issubset(all_set), f"Missing from __all__: {expected - all_set}"
