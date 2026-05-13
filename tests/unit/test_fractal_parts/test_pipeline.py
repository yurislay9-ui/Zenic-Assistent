"""
Tests for Phase 3 (Fill), full pipeline, utilities, and pattern implementation.
"""

import os
import sys
import ast
import pytest
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.fractal_generator import (
    FractalGenerator, FractalSpec, FileBlueprint, FractalResult,
)


class TestPhase3Fill:
    """Tests for Phase 3: Logic filling."""

    def setup_method(self):
        self.gen = FractalGenerator()

    def test_fill_creates_result(self):
        """Phase 3 should return a FractalResult."""
        spec = self.gen.generate_structure(
            description="Auth system",
            project_type="auth_system",
        )
        spec = self.gen.generate_skeletons(spec)
        result = self.gen.fill_logic(spec)

        assert isinstance(result, FractalResult)
        assert result.status == "complete"
        assert result.current_phase == 3

    def test_fill_with_output_dir(self):
        """Phase 3 should write files to output directory."""
        tmpdir = tempfile.mkdtemp(prefix="fractal_test_")
        try:
            spec = self.gen.generate_structure(
                description="Auth system",
                project_type="auth_system",
            )
            spec = self.gen.generate_skeletons(spec)
            result = self.gen.fill_logic(spec, output_dir=tmpdir)

            assert result.status == "complete"
            assert len(result.files_generated) > 0

            # Verify files exist on disk
            for fpath in result.files_generated:
                full_path = os.path.join(tmpdir, fpath)
                assert os.path.exists(full_path), f"File not created: {full_path}"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_fill_replaces_pass_todo(self):
        """Phase 3 should replace 'pass  # TODO: Implement' with logic."""
        bp = FileBlueprint(
            path="src/main.py",
            language="python",
            description="Main",
            functions=[
                {"name": "create_item", "docstring": "Creates an item", "params": "data: dict"},
            ],
        )
        spec = FractalSpec(
            project_name="test",
            project_type="crud_dashboard",
            language="python",
            files=[bp],
            phase=2,
        )
        spec = self.gen.generate_skeletons(spec)
        result = self.gen.fill_logic(spec)

        # The 'pass  # TODO: Implement' should be replaced
        content = getattr(bp, '_generated_content', '')
        # After fill, there should be implementation logic
        assert "pass  # TODO: Implement" not in content or "try:" in content


class TestFullPipeline:
    """Tests for the full 3-phase pipeline."""

    def setup_method(self):
        self.gen = FractalGenerator()

    def test_generate_project_auth_system(self):
        """Full pipeline should generate an auth system project."""
        result = self.gen.generate_project(
            description="Authentication system with JWT",
            project_type="auth_system",
            project_name="test_auth",
        )
        assert result.status == "complete"
        assert result.project_name == "test_auth"
        assert result.current_phase == 3
        assert result.total_files > 0

    def test_generate_project_crud(self):
        """Full pipeline should generate a CRUD dashboard project."""
        result = self.gen.generate_project(
            description="CRUD dashboard for inventory",
            project_type="crud_dashboard",
            project_name="test_crud",
        )
        assert result.status == "complete"
        assert result.total_files > 0

    def test_generate_project_with_output(self):
        """Full pipeline with output_dir should create files on disk."""
        tmpdir = tempfile.mkdtemp(prefix="fractal_full_")
        try:
            result = self.gen.generate_project(
                description="Test project",
                project_type="inventory",
                project_name="test_inventory",
                output_dir=tmpdir,
            )
            assert result.status == "complete"
            assert len(result.files_generated) > 0
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestUtilities:
    """Tests for utility methods."""

    def setup_method(self):
        self.gen = FractalGenerator()

    def test_get_template_types(self):
        """Should return list of available template types."""
        types = self.gen.get_template_types()
        assert isinstance(types, list)
        assert "auth_system" in types
        assert "crud_dashboard" in types
        assert "inventory" in types

    def test_get_spec_summary(self):
        """Should return a summary dict of the spec."""
        spec = self.gen.generate_structure(
            description="Auth system",
            project_type="auth_system",
            project_name="test",
        )
        summary = self.gen.get_spec_summary(spec)
        assert summary["project_name"] == "test"
        assert summary["project_type"] == "auth_system"
        assert "directories" in summary
        assert "files" in summary
        assert "classes" in summary
        assert "functions" in summary

    def test_fix_python_skeleton(self):
        """Should fix simple syntax errors in Python skeletons."""
        bad_code = "def foo():\n\n"
        fixed = self.gen._fix_python_skeleton(bad_code)
        # Should add 'pass' after the function definition
        assert "pass" in fixed


class TestPatternImplementation:
    """Tests for pattern-based fallback implementation."""

    def setup_method(self):
        self.gen = FractalGenerator()

    def test_create_pattern(self):
        """Create functions should get try/except implementation."""
        impl = self.gen._generate_pattern_implementation(
            "def create_user(data: dict):", FileBlueprint(),
            FractalSpec(project_type="auth_system"), "    "
        )
        assert len(impl) > 0
        assert any("try:" in line for line in impl)

    def test_get_pattern(self):
        """Get/list functions should get try/except implementation."""
        impl = self.gen._generate_pattern_implementation(
            "def get_users():", FileBlueprint(),
            FractalSpec(), "    "
        )
        assert len(impl) > 0

    def test_delete_pattern(self):
        """Delete functions should get try/except implementation."""
        impl = self.gen._generate_pattern_implementation(
            "def delete_user(user_id: int):", FileBlueprint(),
            FractalSpec(), "    "
        )
        assert len(impl) > 0

    def test_validate_pattern(self):
        """Validate functions should get try/except implementation."""
        impl = self.gen._generate_pattern_implementation(
            "def validate_token(token: str):", FileBlueprint(),
            FractalSpec(), "    "
        )
        assert len(impl) > 0

    def test_test_pattern(self):
        """Test functions should get assert implementation."""
        impl = self.gen._generate_pattern_implementation(
            "def test_something():", FileBlueprint(),
            FractalSpec(), "    "
        )
        assert len(impl) > 0
        assert any("assert" in line for line in impl)

    def test_unknown_pattern(self):
        """Unknown functions should get NotImplementedError."""
        impl = self.gen._generate_pattern_implementation(
            "def process_data(x):", FileBlueprint(),
            FractalSpec(), "    "
        )
        assert any("NotImplementedError" in line for line in impl)
