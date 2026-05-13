"""
Tests for NicheLoader query, search, and compliance filtering.
"""

import pytest

from src.core.niche_loader import (
    NicheLoader, NicheTemplate, YAML_AVAILABLE,
)


# ============================================================
#  Query Tests
# ============================================================

class TestNicheQuery:
    """Tests for niche retrieval and search."""

    def test_get_by_name(self, loaded_niche_loader):
        """Should retrieve a niche by exact name."""
        niche = loaded_niche_loader.get("clinic_management")
        assert niche is not None
        assert niche.name == "clinic_management"

    def test_get_nonexistent(self, loaded_niche_loader):
        """Should return None for nonexistent niche name."""
        assert loaded_niche_loader.get("nonexistent") is None

    def test_get_plan(self, loaded_niche_loader):
        """Should return a CompositionPlan for a niche."""
        plan = loaded_niche_loader.get_plan("clinic_management")
        assert plan is not None
        assert "jwt_auth" in plan.blocks

    def test_get_plan_nonexistent(self, loaded_niche_loader):
        """Should return None for nonexistent niche plan."""
        assert loaded_niche_loader.get_plan("nonexistent") is None

    def test_list_domains(self, loaded_niche_loader):
        """Should list all available domains."""
        domains = loaded_niche_loader.list_domains()
        assert "healthcare" in domains
        assert "hospitality" in domains

    def test_list_niches_all(self, loaded_niche_loader):
        """Should list all niche names."""
        niches = loaded_niche_loader.list_niches()
        assert "clinic_management" in niches
        assert "restaurant_pos" in niches

    def test_list_niches_by_domain(self, loaded_niche_loader):
        """Should filter niches by domain."""
        niches = loaded_niche_loader.list_niches(domain="healthcare")
        assert "clinic_management" in niches
        assert "restaurant_pos" not in niches

    def test_get_by_domain(self, loaded_niche_loader):
        """Should return all niches for a domain."""
        niches = loaded_niche_loader.get_by_domain("healthcare")
        assert len(niches) >= 1
        assert all(n.domain == "healthcare" for n in niches)


# ============================================================
#  Search Tests
# ============================================================

class TestNicheSearch:
    """Tests for keyword-based niche search."""

    def test_search_by_name(self, loaded_niche_loader):
        """Should find niche by name match."""
        results = loaded_niche_loader.search("clinic_management")
        assert len(results) >= 1
        assert any(n.name == "clinic_management" for n in results)

    def test_search_by_domain(self, loaded_niche_loader):
        """Should find niches by domain match."""
        results = loaded_niche_loader.search("healthcare")
        assert len(results) >= 1

    def test_search_by_description_keywords(self, loaded_niche_loader):
        """Should find niches matching description keywords."""
        results = loaded_niche_loader.search("appointment scheduling")
        assert len(results) >= 1

    def test_search_no_results(self, loaded_niche_loader):
        """Should return empty for no matching query."""
        results = loaded_niche_loader.search("quantum_computing_space_station")
        assert results == []

    def test_search_respects_limit(self, loaded_niche_loader):
        """Should respect the limit parameter."""
        results = loaded_niche_loader.search("management", limit=1)
        assert len(results) <= 1

    def test_suggest_for_description(self, loaded_niche_loader):
        """Should suggest niches with relevance scores."""
        suggestions = loaded_niche_loader.suggest_for_description(
            "healthcare clinic with patient management"
        )
        assert len(suggestions) >= 1
        assert "relevance_score" in suggestions[0]
        assert "name" in suggestions[0]


# ============================================================
#  Compliance Filtering Tests
# ============================================================

class TestComplianceFiltering:
    """Tests for compliance and risk-based filtering."""

    def test_filter_by_compliance(self, loaded_niche_loader):
        """Should filter niches by compliance regulation."""
        hipaa = loaded_niche_loader.filter_by_compliance("HIPAA")
        assert len(hipaa) >= 1
        assert any(n.name == "clinic_management" for n in hipaa)

    def test_filter_by_compliance_no_match(self, loaded_niche_loader):
        """Should return empty when no niches match compliance."""
        results = loaded_niche_loader.filter_by_compliance("SOX")
        assert results == []

    def test_filter_by_sensitivity(self, loaded_niche_loader):
        """Should filter niches by data sensitivity level."""
        high = loaded_niche_loader.filter_by_sensitivity("high")
        assert len(high) >= 1
        assert all(n.data_sensitivity == "high" for n in high)

    def test_filter_by_scale(self, loaded_niche_loader):
        """Should filter niches by scale."""
        small = loaded_niche_loader.filter_by_scale("small")
        assert len(small) >= 1
        assert all(n.scale == "small" for n in small)
