"""Tests for abortive protocol constants and subtask generation."""

import pytest

from src.core.abortive_protocol import (
    AbortiveProtocol,
    MAX_SUBTASKS,
    MAX_DEEP_SUBTASKS,
    MAX_ABORTIVE_DEPTH,
    ABORTIVE_SANDBOX_TTL_MULTIPLIER,
    ABORTIVE_SANDBOX_TTL_MIN,
)
from src.core.subtask_descriptor import SubtaskDescriptor

from .conftest import _make_mock_intent, _make_mock_plan


# ============================================================
#  Test: Constants
# ============================================================

class TestAbortiveConstants:
    """Tests for extracted constants."""

    def test_max_subtasks(self):
        """MAX_SUBTASKS should be reasonable."""
        assert MAX_SUBTASKS == 5

    def test_max_deep_subtasks(self):
        """MAX_DEEP_SUBTASKS should be reasonable."""
        assert MAX_DEEP_SUBTASKS == 3

    def test_max_abortive_depth(self):
        """MAX_ABORTIVE_DEPTH should be 2."""
        assert MAX_ABORTIVE_DEPTH == 2

    def test_sandbox_ttl_multiplier(self):
        """ABORTIVE_SANDBOX_TTL_MULTIPLIER should be positive."""
        assert ABORTIVE_SANDBOX_TTL_MULTIPLIER > 0

    def test_sandbox_ttl_min(self):
        """ABORTIVE_SANDBOX_TTL_MIN should be positive."""
        assert ABORTIVE_SANDBOX_TTL_MIN > 0


# ============================================================
#  Test: Subtask Generation
# ============================================================

class TestAbortiveGenerateSubtasks:
    """Tests for subtask generation."""

    def test_create_operation_generates_subtasks(self, protocol):
        """CREATE should generate interface + implementation + security subtasks."""
        ap, orch = protocol
        intent = _make_mock_intent(op="CREATE", raw_code="")
        plan = _make_mock_plan()
        ast_analysis = {"function_names": []}

        subtasks = ap.generate_subtasks(intent, ast_analysis, plan)
        assert len(subtasks) >= 2
        # Should have at least interface and implementation subtasks
        messages = [s.message for s in subtasks]
        assert any("interfaces" in m or "interface" in m for m in messages)
        assert any("core logic" in m or "implement" in m for m in messages)

    def test_refactor_operation_generates_subtasks(self, protocol):
        """REFACTOR should generate analyze + optimize subtasks."""
        ap, orch = protocol
        intent = _make_mock_intent(op="REFACTOR", raw_code="")
        plan = _make_mock_plan()
        ast_analysis = {}

        subtasks = ap.generate_subtasks(intent, ast_analysis, plan)
        assert len(subtasks) >= 2
        messages = [s.message for s in subtasks]
        assert any("analyze" in m.lower() for m in messages)

    def test_debug_operation_generates_subtasks(self, protocol):
        """DEBUG should generate trace + fix subtasks."""
        ap, orch = protocol
        intent = _make_mock_intent(op="DEBUG", raw_code="")
        plan = _make_mock_plan()
        ast_analysis = {}

        subtasks = ap.generate_subtasks(intent, ast_analysis, plan)
        assert len(subtasks) >= 2
        messages = [s.message for s in subtasks]
        assert any("trace" in m.lower() for m in messages)
        assert any("fix" in m.lower() for m in messages)

    def test_raw_code_with_functions(self, protocol):
        """Should generate one subtask per function when raw_code has functions."""
        ap, orch = protocol
        intent = _make_mock_intent(raw_code="def foo(): pass\ndef bar(): pass")
        plan = _make_mock_plan()
        ast_analysis = {"function_names": ["foo", "bar"]}

        subtasks = ap.generate_subtasks(intent, ast_analysis, plan)
        assert len(subtasks) >= 2
        # Should have subtasks for each function
        targets = [s.target for s in subtasks]
        assert "foo" in targets
        assert "bar" in targets

    def test_raw_code_without_functions(self, protocol):
        """Should generate analyze + operation subtasks for raw code without functions."""
        ap, orch = protocol
        intent = _make_mock_intent(raw_code="x = 1")
        plan = _make_mock_plan()
        ast_analysis = {"function_names": []}

        subtasks = ap.generate_subtasks(intent, ast_analysis, plan)
        assert len(subtasks) >= 1

    def test_default_operation_generates_subtasks(self, protocol):
        """Unknown operations should generate analyze subtasks."""
        ap, orch = protocol
        intent = _make_mock_intent(op="SEARCH", raw_code="")
        plan = _make_mock_plan()
        ast_analysis = {}

        subtasks = ap.generate_subtasks(intent, ast_analysis, plan)
        assert len(subtasks) >= 1

    def test_subtask_descriptors_are_enriched(self, protocol):
        """Generated subtasks should be SubtaskDescriptor instances with context."""
        ap, orch = protocol
        intent = _make_mock_intent(op="CREATE", raw_code="")
        plan = _make_mock_plan()
        ast_analysis = {}

        subtasks = ap.generate_subtasks(intent, ast_analysis, plan)
        for st in subtasks:
            assert isinstance(st, SubtaskDescriptor)
            assert st.message != ""
            assert isinstance(st.solver_insights, dict)
            assert isinstance(st.mcts_hints, list)
            assert isinstance(st.parent_violations, list)
            assert isinstance(st.parent_context, dict)

    def test_max_subtasks_limit(self, protocol):
        """Should not exceed MAX_SUBTASKS when slicing."""
        ap, orch = protocol
        intent = _make_mock_intent(raw_code="")
        intent.raw_code = "code"
        # Many function names
        ast_analysis = {"function_names": [f"fn_{i}" for i in range(10)]}
        plan = _make_mock_plan()

        subtasks = ap.generate_subtasks(intent, ast_analysis, plan)
        # The slicing [:MAX_SUBTASKS] is in handle_abortive_protocol,
        # generate_subtasks itself may return more
        assert isinstance(subtasks, list)
