"""
Tests for Phase 1 (Structural) and Phase 2 (Skeletons) generation.
"""

import os
import sys
import ast
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.fractal_generator import (
    FractalGenerator, FractalSpec, FileBlueprint, FractalResult,
)


class TestPhase1Structural:
    """Tests for Phase 1: Structural generation."""

    def setup_method(self):
        self.gen = FractalGenerator()

    def test_generate_structure_auth_system(self):
        """Phase 1 should generate auth_system structure."""
        spec = self.gen.generate_structure(
            description="Authentication system",
            project_type="auth_system",
            project_name="my_auth",
        )
        assert spec.project_name == "my_auth"
        assert spec.phase == 1
        assert len(spec.files) > 0
        assert len(spec.directories) > 0

    def test_generate_structure_unknown_type_uses_default(self):
        """Phase 1 should use DEFAULT_TEMPLATE for unknown types."""
        spec = self.gen.generate_structure(
            description="Unknown project",
            project_type="nonexistent_type",
            project_name="test",
        )
        assert spec.project_name == "test"
        assert len(spec.files) > 0  # Default template has files

    def test_generate_structure_has_config_files(self):
        """Phase 1 should include config files."""
        spec = self.gen.generate_structure(
            description="Auth system",
            project_type="auth_system",
        )
        assert len(spec.config_files) > 0

    def test_generate_structure_files_have_paths(self):
        """All files in spec should have a path."""
        spec = self.gen.generate_structure(
            description="CRUD dashboard",
            project_type="crud_dashboard",
        )
        for f in spec.files:
            assert f.path, f"File missing path: {f}"


class TestPhase2Skeletons:
    """Tests for Phase 2: Skeleton generation."""

    def setup_method(self):
        self.gen = FractalGenerator()

    def test_generate_python_skeleton(self):
        """Phase 2 should generate valid Python skeleton code."""
        bp = FileBlueprint(
            path="src/models/user.py",
            language="python",
            description="User model",
            classes=[
                {"name": "User", "docstring": "User model", "bases": "Base"},
            ],
            functions=[
                {"name": "create_user", "docstring": "Creates a user", "params": "data: dict"},
            ],
            imports=["from sqlalchemy import Column, Integer, String"],
        )
        skeleton = self.gen._generate_python_skeleton(bp)

        # Should contain imports
        assert "from sqlalchemy import Column, Integer, String" in skeleton
        # Should contain class
        assert "class User(Base):" in skeleton
        # Should contain docstring
        assert "User model" in skeleton
        # Should contain function
        assert "def create_user(data: dict):" in skeleton
        # Should contain pass placeholder
        assert "pass" in skeleton

    def test_generate_python_skeleton_valid_syntax(self):
        """Python skeleton should be valid syntax (AST parseable)."""
        bp = FileBlueprint(
            path="src/main.py",
            language="python",
            description="Main app",
            classes=[
                {"name": "App", "docstring": "Application class", "bases": ""},
            ],
            functions=[
                {"name": "run", "docstring": "Run the app", "params": ""},
            ],
        )
        skeleton = self.gen._generate_python_skeleton(bp)
        # Should parse without errors
        ast.parse(skeleton)

    def test_generate_js_skeleton(self):
        """Phase 2 should generate valid JavaScript skeleton."""
        bp = FileBlueprint(
            path="src/app.js",
            language="javascript",
            description="Main app",
            classes=[
                {"name": "App", "docstring": "Application", "bases": ""},
            ],
            functions=[
                {"name": "init", "docstring": "Initialize", "params": ""},
            ],
        )
        skeleton = self.gen._generate_js_skeleton(bp)
        assert "class App" in skeleton
        assert "function init" in skeleton

    def test_generate_kotlin_skeleton(self):
        """Phase 2 should generate valid Kotlin skeleton."""
        bp = FileBlueprint(
            path="src/Main.kt",
            language="kotlin",
            description="Main app",
            classes=[
                {"name": "Main", "docstring": "Main class", "bases": ""},
            ],
            functions=[
                {"name": "main", "docstring": "Entry point", "params": ""},
            ],
        )
        skeleton = self.gen._generate_kotlin_skeleton(bp)
        assert "class Main" in skeleton
        assert "fun main" in skeleton

    def test_full_skeleton_generation(self):
        """Full Phase 2 should add _generated_content to all files."""
        spec = self.gen.generate_structure(
            description="Auth system",
            project_type="auth_system",
        )
        spec = self.gen.generate_skeletons(spec)

        assert spec.phase == 2
        for f in spec.files:
            content = f.generated_content
            # All non-init files should have content
            if not f.path.endswith("__init__.py") or f.classes or f.functions:
                assert content, f"No content for {f.path}"
