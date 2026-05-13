"""
Tests for FractalSpec, FileBlueprint data models, and project templates.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.fractal_generator import (
    FractalGenerator, FractalSpec, FileBlueprint, FractalResult,
    PROJECT_TEMPLATES, DEFAULT_TEMPLATE,
)


class TestFractalSpec:
    """Tests for FractalSpec data structure."""

    def test_default_spec(self):
        """FractalSpec should have sensible defaults."""
        spec = FractalSpec()
        assert spec.project_name == ""
        assert spec.phase == 0
        assert spec.directories == []
        assert spec.files == []
        assert spec.config_files == {}

    def test_spec_with_data(self):
        """FractalSpec should accept construction parameters."""
        spec = FractalSpec(
            project_name="test_project",
            project_type="auth_system",
            language="python",
            description="A test auth system",
            directories=["src/", "tests/"],
            files=[FileBlueprint(path="src/main.py")],
            phase=1,
        )
        assert spec.project_name == "test_project"
        assert spec.project_type == "auth_system"
        assert len(spec.directories) == 2
        assert len(spec.files) == 1
        assert spec.phase == 1


class TestFileBlueprint:
    """Tests for FileBlueprint data structure."""

    def test_default_blueprint(self):
        """FileBlueprint should have sensible defaults."""
        bp = FileBlueprint()
        assert bp.path == ""
        assert bp.language == "python"
        assert bp.classes == []
        assert bp.functions == []
        assert bp.imports == []

    def test_blueprint_with_classes(self):
        """FileBlueprint should hold class definitions."""
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
            imports=["from sqlalchemy import Column"],
        )
        assert bp.path == "src/models/user.py"
        assert len(bp.classes) == 1
        assert len(bp.functions) == 1
        assert bp.classes[0]["name"] == "User"
        assert bp.functions[0]["params"] == "data: dict"


class TestProjectTemplates:
    """Tests for built-in project templates."""

    def test_auth_system_template_exists(self):
        """auth_system template should be available."""
        assert "auth_system" in PROJECT_TEMPLATES

    def test_crud_dashboard_template_exists(self):
        """crud_dashboard template should be available."""
        assert "crud_dashboard" in PROJECT_TEMPLATES

    def test_inventory_template_exists(self):
        """inventory template should be available."""
        assert "inventory" in PROJECT_TEMPLATES

    def test_auth_system_has_required_files(self):
        """auth_system template should have models, routes, services, main."""
        template = PROJECT_TEMPLATES["auth_system"]
        paths = [f["path"] for f in template["files"]]
        assert any("models" in p for p in paths)
        assert any("routes" in p for p in paths)
        assert any("services" in p for p in paths)
        assert any("main.py" in p for p in paths)

    def test_auth_system_has_config_files(self):
        """auth_system template should have requirements.txt."""
        template = PROJECT_TEMPLATES["auth_system"]
        assert "requirements.txt" in template["config_files"]

    def test_default_template_exists(self):
        """DEFAULT_TEMPLATE should be available for unknown types."""
        assert DEFAULT_TEMPLATE is not None
        assert len(DEFAULT_TEMPLATE["files"]) > 0
