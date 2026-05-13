"""
Tests for static code generation and pipeline feature module generation.
"""

import pytest

from src.core.code_generator import CodeGenerator
from src.core.shared.contracts import ExecutionPlan, OperationType, GoalType, IntentPayload


class TestStaticCodeGeneration:
    """Tests for static code generation methods."""

    def test_generate_security_module(self):
        """Should generate a security module."""
        code = CodeGenerator.generate_security_module("auth")
        assert isinstance(code, str)
        assert "SecurityManager" in code
        assert "hash_password" in code
        assert "verify_password" in code
        assert "generate_token" in code

    def test_generate_feature_module(self):
        """Should generate a feature module."""
        code = CodeGenerator.generate_feature_module(
            "my_feature",
            existing_functions=["func1", "func2"],
            existing_classes=["MyClass"],
            needed_imports={"os", "sys"},
        )
        assert isinstance(code, str)
        assert "My_featureManager" in code
        assert "func1" in code
        assert "MyClass" in code

    def test_generate_feature_module_no_existing(self):
        """Should generate a feature module without existing code context."""
        code = CodeGenerator.generate_feature_module(
            "standalone",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
        )
        assert isinstance(code, str)
        assert "StandaloneManager" in code

    def test_generate_kotlin_contextual(self):
        """Should generate Kotlin code."""
        code = CodeGenerator.generate_kotlin_contextual(None, "auth", [])
        assert isinstance(code, str)
        assert "package com.zenic" in code
        assert "auth" in code.lower()
        assert "class" in code

    def test_generate_go_contextual(self):
        """Should generate Go code."""
        code = CodeGenerator.generate_go_contextual(None, "handler")
        assert isinstance(code, str)
        assert "package main" in code
        assert "Manager" in code

    def test_generate_javascript_contextual(self):
        """Should generate JavaScript code."""
        code = CodeGenerator.generate_javascript_contextual(None, "service")
        assert isinstance(code, str)
        assert "ServiceManager" in code
        assert "module.exports" in code

    def test_generate_kotlin_with_existing_classes(self):
        """Should reference existing classes in Kotlin generation."""
        code = CodeGenerator.generate_kotlin_contextual(None, "auth", ["BaseService"])
        assert isinstance(code, str)

    def test_generate_go_empty_target(self):
        """Should handle empty target name for Go."""
        code = CodeGenerator.generate_go_contextual(None, "")
        assert isinstance(code, str)

    def test_generate_javascript_empty_target(self):
        """Should handle empty target name for JavaScript."""
        code = CodeGenerator.generate_javascript_contextual(None, "")
        assert isinstance(code, str)


class TestPipelineFeatureModule:
    """Tests for generate_pipeline_feature_module method."""

    def test_basic_pipeline_module(self, code_gen):
        """Should generate a pipeline feature module."""
        code = code_gen.generate_pipeline_feature_module(
            safe_target="pipeline_mod",
            existing_functions=["func_a"],
            existing_classes=["ClassA"],
            needed_imports=set(),
            solver_insights=CodeGenerator.extract_solver_insights(None),
            mcts_actions=["ANALYZE_CODE"],
        )
        assert isinstance(code, str)
        assert "Pipeline_modManager" in code

    def test_pipeline_module_with_null_safety(self, code_gen):
        """Should include null-safety guard when solver requires it."""
        solver_insights = CodeGenerator.extract_solver_insights(None)
        solver_insights["null_safety_required"] = True
        solver_insights["status"] = "PROVEN"

        code = code_gen.generate_pipeline_feature_module(
            safe_target="safe_mod",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=solver_insights,
            mcts_actions=[],
        )
        assert "_validate_not_none" in code

    def test_pipeline_module_with_type_safety(self, code_gen):
        """Should include type-safety guard when solver requires it."""
        solver_insights = CodeGenerator.extract_solver_insights(None)
        solver_insights["type_safety_required"] = True
        solver_insights["status"] = "PROVEN"

        code = code_gen.generate_pipeline_feature_module(
            safe_target="typed_mod",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=solver_insights,
            mcts_actions=[],
        )
        assert "_validate_type" in code

    def test_pipeline_module_with_critical_target(self, code_gen):
        """Should include sanitization for critical targets."""
        solver_insights = CodeGenerator.extract_solver_insights(None)
        solver_insights["critical_target"] = True
        solver_insights["status"] = "PROVEN"

        code = code_gen.generate_pipeline_feature_module(
            safe_target="critical_mod",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=solver_insights,
            mcts_actions=[],
        )
        assert "_sanitize_input" in code

    def test_pipeline_module_with_symbolic_validation(self, code_gen):
        """Should include invariant assertion for SYMBOLIC_VALIDATION action."""
        code = code_gen.generate_pipeline_feature_module(
            safe_target="validated_mod",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=CodeGenerator.extract_solver_insights(None),
            mcts_actions=["SYMBOLIC_VALIDATION"],
        )
        assert "_assert_invariant" in code

    def test_pipeline_module_with_div_zero_risk(self, code_gen):
        """Should include division guard for division-by-zero risks."""
        solver_insights = CodeGenerator.extract_solver_insights(None)
        solver_insights["division_by_zero_risks"] = ["div by zero at line 5"]

        code = code_gen.generate_pipeline_feature_module(
            safe_target="div_safe",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=solver_insights,
            mcts_actions=[],
        )
        assert "_safe_divide" in code

    def test_pipeline_module_with_index_oob_risk(self, code_gen):
        """Should include index bounds guard for OOB risks."""
        solver_insights = CodeGenerator.extract_solver_insights(None)
        solver_insights["index_oob_risks"] = ["index OOB at line 3"]

        code = code_gen.generate_pipeline_feature_module(
            safe_target="idx_safe",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=solver_insights,
            mcts_actions=[],
        )
        assert "_safe_index" in code

    def test_pipeline_module_with_violated_constraints(self, code_gen):
        """Should include defensive checks for violated constraints."""
        solver_insights = CodeGenerator.extract_solver_insights(None)
        solver_insights["status"] = "VIOLATED"
        solver_insights["violated_constraints"] = ["division by zero found"]

        code = code_gen.generate_pipeline_feature_module(
            safe_target="defended",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=solver_insights,
            mcts_actions=[],
        )
        assert isinstance(code, str)
        assert "violation" in code.lower() or "defensive" in code.lower()

    def test_pipeline_module_with_concrete_test_inputs(self, code_gen):
        """Should generate test cases from concrete symbolic inputs."""
        solver_insights = CodeGenerator.extract_solver_insights(None)
        solver_insights["concrete_test_inputs"] = [
            {"x": 1, "y": 2},
            {"x": 0, "y": -1},
        ]

        code = code_gen.generate_pipeline_feature_module(
            safe_target="tested_mod",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=solver_insights,
            mcts_actions=[],
        )
        assert "Test" in code
        assert "test_case" in code
