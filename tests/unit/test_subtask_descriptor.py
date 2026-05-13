"""
ZENIC-AGENTS - SubtaskDescriptor Tests

Tests for the enriched subtask descriptor:
  - Creation with defaults and explicit values
  - to_message() returns message text
  - to_dict() serialization
  - __repr__ string representation
"""

import pytest
from src.core.subtask_descriptor import SubtaskDescriptor


# ============================================================
#  CREATION TESTS
# ============================================================

class TestSubtaskDescriptorCreation:
    """Tests for creating SubtaskDescriptor instances."""

    def test_create_with_defaults(self):
        """Creating with only message should set all other fields to defaults."""
        desc = SubtaskDescriptor(message="Isolate auth module")
        assert desc.message == "Isolate auth module"
        assert desc.target == ""
        assert desc.operation == ""
        assert desc.goal == ""
        assert desc.solver_insights == {}
        assert desc.mcts_hints == []
        assert desc.parent_violations == []
        assert desc.parent_context == {}
        assert desc.depth == 0

    def test_create_with_all_fields(self):
        """Creating with all fields should preserve them."""
        desc = SubtaskDescriptor(
            message="Apply surgical fix",
            target="auth.py",
            operation="REFACTOR",
            goal="BUG_FIX",
            solver_insights={"constraint": "x > 0"},
            mcts_hints=["expand_node_3"],
            parent_violations=["type_mismatch"],
            parent_context={"complexity": "high", "imports": 5},
            depth=2,
        )
        assert desc.message == "Apply surgical fix"
        assert desc.target == "auth.py"
        assert desc.operation == "REFACTOR"
        assert desc.goal == "BUG_FIX"
        assert desc.solver_insights == {"constraint": "x > 0"}
        assert desc.mcts_hints == ["expand_node_3"]
        assert desc.parent_violations == ["type_mismatch"]
        assert desc.parent_context == {"complexity": "high", "imports": 5}
        assert desc.depth == 2

    def test_create_with_partial_fields(self):
        """Creating with some fields should fill others with defaults."""
        desc = SubtaskDescriptor(
            message="Test",
            target="main.py",
            operation="DEBUG",
        )
        assert desc.message == "Test"
        assert desc.target == "main.py"
        assert desc.operation == "DEBUG"
        assert desc.goal == ""
        assert desc.solver_insights == {}
        assert desc.depth == 0

    def test_solver_insights_not_shared(self):
        """Each instance should get its own solver_insights dict."""
        desc1 = SubtaskDescriptor(message="A")
        desc2 = SubtaskDescriptor(message="B")
        desc1.solver_insights["key"] = "val"
        assert "key" not in desc2.solver_insights

    def test_mcts_hints_not_shared(self):
        """Each instance should get its own mcts_hints list."""
        desc1 = SubtaskDescriptor(message="A")
        desc2 = SubtaskDescriptor(message="B")
        desc1.mcts_hints.append("hint1")
        assert len(desc2.mcts_hints) == 0


# ============================================================
#  SERIALIZATION TESTS
# ============================================================

class TestSubtaskDescriptorSerialization:
    """Tests for serialization methods."""

    def test_to_message_returns_message(self):
        """to_message() should return the message text."""
        desc = SubtaskDescriptor(message="Create login module")
        assert desc.to_message() == "Create login module"

    def test_to_dict_keys(self):
        """to_dict() should include all expected keys."""
        desc = SubtaskDescriptor(
            message="Fix auth",
            target="auth.py",
            operation="DEBUG",
            goal="BUG_FIX",
            solver_insights={"z3": "unsat"},
            mcts_hints=["hint_a"],
            parent_violations=["err1", "err2"],
            parent_context={"ast_depth": 4},
            depth=1,
        )
        d = desc.to_dict()
        assert d["message"] == "Fix auth"
        assert d["target"] == "auth.py"
        assert d["operation"] == "DEBUG"
        assert d["goal"] == "BUG_FIX"
        assert d["solver_insights"] == {"z3": "unsat"}
        assert d["mcts_hints"] == ["hint_a"]
        assert d["parent_violations_count"] == 2
        assert d["depth"] == 1

    def test_to_dict_violations_count(self):
        """to_dict() should report violation count, not the full list."""
        desc = SubtaskDescriptor(
            message="test",
            parent_violations=["v1", "v2", "v3"],
        )
        d = desc.to_dict()
        assert d["parent_violations_count"] == 3
        # Should NOT include the full violations list
        assert "parent_violations" not in d or d.get("parent_violations_count") == 3

    def test_to_dict_preserves_solver_insights(self):
        """to_dict() should include solver_insights as-is."""
        insights = {"constraint_set": ["a > b"], "solution": {"a": 5}}
        desc = SubtaskDescriptor(message="test", solver_insights=insights)
        d = desc.to_dict()
        assert d["solver_insights"] == insights


# ============================================================
#  REPRESENTATION TESTS
# ============================================================

class TestSubtaskDescriptorRepr:
    """Tests for __repr__ output."""

    def test_repr_includes_key_fields(self):
        """__repr__ should include message, target, operation, goal, depth."""
        desc = SubtaskDescriptor(
            message="Fix bug",
            target="app.py",
            operation="DEBUG",
            goal="BUG_FIX",
            depth=1,
        )
        r = repr(desc)
        assert "Fix bug" in r
        assert "app.py" in r
        assert "DEBUG" in r
        assert "BUG_FIX" in r
        assert "depth=1" in r

    def test_repr_format(self):
        """__repr__ should follow SubtaskDescriptor(...) format."""
        desc = SubtaskDescriptor(message="Test", target="t.py", operation="CREATE", goal="FEATURE_ADD", depth=0)
        r = repr(desc)
        assert r.startswith("SubtaskDescriptor(")
        assert r.endswith(")")

    def test_repr_empty_fields(self):
        """__repr__ with empty fields should work correctly."""
        desc = SubtaskDescriptor(message="")
        r = repr(desc)
        assert "message=''" in r
