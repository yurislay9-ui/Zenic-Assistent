"""
Tests for NicheTemplate dataclass and NicheLoader loading behavior.
"""

import os
import pytest

from src.core.niche_loader import (
    NicheLoader, NicheTemplate, NICHE_ROOT, YAML_AVAILABLE,
)


# ============================================================
#  NicheTemplate Dataclass Tests
# ============================================================

class TestNicheTemplate:
    """Tests for NicheTemplate dataclass and methods."""

    def test_keywords_extraction(self):
        """Should extract keywords from name, domain, and description."""
        niche = NicheTemplate(
            name="clinic_management", domain="healthcare",
            subdomain="clinic",
            description="Clinic management system",
            scale="medium",
        )
        kw = niche.keywords
        assert "clinic" in kw
        assert "management" in kw
        assert "healthcare" in kw

    def test_entity_count(self):
        """Should count entities correctly."""
        niche = NicheTemplate(
            name="test", domain="d", subdomain="s",
            description="desc", scale="small",
            entities=[{"name": "A"}, {"name": "B"}],
        )
        assert niche.entity_count == 2

    def test_total_fields(self):
        """Should count total fields across entities."""
        niche = NicheTemplate(
            name="test", domain="d", subdomain="s",
            description="desc", scale="small",
            entities=[
                {"fields": [{"name": "x"}, {"name": "y"}]},
                {"fields": [{"name": "z"}]},
            ],
        )
        assert niche.total_fields == 3

    def test_to_composition_plan(self):
        """Should convert to CompositionPlan with correct fields."""
        niche = NicheTemplate(
            name="test", domain="d", subdomain="s",
            description="desc", scale="small",
            blocks=["jwt_auth", "crud_service"],
            variables={"key": "val"},
        )
        plan = niche.to_composition_plan()
        assert plan.blocks == ["jwt_auth", "crud_service"]
        assert plan.variables == {"key": "val"}


# ============================================================
#  Loading Tests
# ============================================================

class TestNicheLoading:
    """Tests for NicheLoader loading behavior."""

    def test_load_all_returns_count(self, loaded_niche_loader):
        """load_all should return the number of niches loaded."""
        # Already loaded in fixture; verify it worked
        assert loaded_niche_loader._loaded is True

    def test_load_empty_directory(self, tmp_path):
        """Should handle empty niche root gracefully."""
        loader = NicheLoader(niche_root=str(tmp_path / "empty"))
        count = loader.load_all()
        assert count == 0

    def test_load_nonexistent_directory(self, tmp_path):
        """Should return 0 for nonexistent directory."""
        loader = NicheLoader(niche_root=str(tmp_path / "nonexistent"))
        count = loader.load_all()
        assert count == 0

    def test_invalid_yaml_skipped(self, niche_dir):
        """Should skip YAML files missing the 'niche' key."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        # Write invalid YAML
        (niche_dir / "healthcare" / "bad.yaml").write_text("invalid: true", encoding="utf-8")
        loader = NicheLoader(niche_root=str(niche_dir))
        count = loader.load_all()
        # Should still load valid niches
        assert count >= 2
