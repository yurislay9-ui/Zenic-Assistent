"""Tests for DNALoader dataclasses and loading logic."""

import pytest

from src.core.dna_loader import (
    DNALoader, LogicModule, DomainRule, YAML_AVAILABLE,
)


# ============================================================
#  LogicModule Dataclass Tests
# ============================================================

class TestLogicModule:
    """Tests for LogicModule dataclass."""

    def test_create_logic_module(self):
        """Should create with all fields."""
        mod = LogicModule(
            id="test_mod", domain="auth", description="Test module",
            code_block="pass", dependencies=["dep1"],
            verification_rule="rule1", inputs=["in1"], outputs=["out1"],
        )
        assert mod.id == "test_mod"
        assert mod.domain == "auth"
        assert mod.dependencies == ["dep1"]

    def test_default_lists(self):
        """Should default to empty lists for list fields."""
        mod = LogicModule(id="m1", domain="d", description="desc", code_block="code")
        assert mod.dependencies == []
        assert mod.inputs == []
        assert mod.outputs == []

    def test_verification_rule_default(self):
        """Verification rule should default to empty string."""
        mod = LogicModule(id="m1", domain="d", description="desc", code_block="code")
        assert mod.verification_rule == ""


# ============================================================
#  DomainRule Dataclass Tests
# ============================================================

class TestDomainRule:
    """Tests for DomainRule dataclass."""

    def test_create_domain_rule(self):
        """Should create with mandatory and optional fields."""
        rule = DomainRule(
            name="healthcare", display_name="Healthcare",
            description="Healthcare rules",
            mandatory_logic=["hipaa"],
            compliance_requirements=["HIPAA"],
        )
        assert rule.name == "healthcare"
        assert rule.mandatory_logic == ["hipaa"]

    def test_default_fields(self):
        """Should default to empty lists for optional fields."""
        rule = DomainRule(name="x", display_name="X", description="d")
        assert rule.ux_patterns == []
        assert rule.edge_cases == []

    def test_notification_triggers_default(self):
        """Notification triggers should default to empty list."""
        rule = DomainRule(name="x", display_name="X", description="d")
        assert rule.notification_triggers == []


# ============================================================
#  DNALoader Loading Tests
# ============================================================

class TestDNALoading:
    """Tests for DNALoader.load_all and individual loaders."""

    def test_load_all_returns_counts(self, populated_dna_loader):
        """load_all should return counts for each template type."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        counts = populated_dna_loader.load_all()
        assert "logic_modules" in counts
        assert "domain_rules" in counts
        assert "validation_gates" in counts
        assert "glossary_entries" in counts

    def test_load_logic_modules(self, populated_dna_loader):
        """Should load logic modules from YAML."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        mod = populated_dna_loader.get_module("auth_jwt_standard")
        assert mod is not None
        assert mod.domain == "authentication"

    def test_load_domain_rules(self, populated_dna_loader):
        """Should load domain expert rules from YAML."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        rule = populated_dna_loader.get_domain_rules("healthcare")
        assert rule is not None
        assert "HIPAA" in rule.compliance_requirements

    def test_load_validation_gates(self, populated_dna_loader):
        """Should load validation gates from YAML."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        gates = populated_dna_loader.get_global_gates()
        assert len(gates) > 0
        # Domain-specific gates should not appear in global
        assert all(g.category != "domain_specific" for g in gates)

    def test_load_glossary(self, populated_dna_loader):
        """Should load glossary entries from YAML."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        polished = populated_dna_loader.polish_text("refactor the code")
        assert "optimize" in polished.lower()

    def test_load_empty_directory(self, dna_loader):
        """Should handle empty DNA root gracefully."""
        counts = dna_loader.load_all()
        assert counts["logic_modules"] == 0
        assert counts["domain_rules"] == 0
        assert counts["validation_gates"] == 0
        assert counts["glossary_entries"] == 0

    def test_load_nonexistent_directory(self, tmp_path):
        """Should handle nonexistent DNA root gracefully."""
        loader = DNALoader(dna_root=str(tmp_path / "nonexistent"))
        counts = loader.load_all()
        assert all(v == 0 for v in counts.values())


# ============================================================
#  Logic Module Query Tests
# ============================================================

class TestLogicModuleQuery:
    """Tests for logic module retrieval and search."""

    def test_get_module_auto_loads(self, populated_dna_loader):
        """get_module should auto-load if not yet loaded."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        # Don't call load_all first
        mod = populated_dna_loader.get_module("auth_jwt_standard")
        assert mod is not None

    def test_get_module_not_found(self, populated_dna_loader):
        """Should return None for nonexistent module."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        mod = populated_dna_loader.get_module("nonexistent_module")
        assert mod is None

    def test_get_modules_by_domain(self, populated_dna_loader):
        """Should return all modules for a specific domain."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        mods = populated_dna_loader.get_modules_by_domain("authentication")
        assert len(mods) >= 1
        assert all(m.domain == "authentication" for m in mods)

    def test_search_modules_by_description(self, populated_dna_loader):
        """Should find modules matching description keywords."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        results = populated_dna_loader.search_modules("JWT authentication")
        assert len(results) >= 1
        assert any(m.id == "auth_jwt_standard" for m in results)


# ============================================================
#  Domain Rule Query Tests
# ============================================================

class TestDomainRuleQuery:
    """Tests for domain rule retrieval."""

    def test_get_mandatory_logic(self, populated_dna_loader):
        """Should return mandatory logic for an industry."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        mandatory = populated_dna_loader.get_mandatory_logic("healthcare")
        assert len(mandatory) > 0

    def test_find_industry_for_niche_direct(self, populated_dna_loader):
        """Should find industry by direct name match."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        rule = populated_dna_loader.find_industry_for_niche("healthcare")
        assert rule is not None
        assert rule.name == "healthcare"

    def test_find_industry_for_niche_partial(self, populated_dna_loader):
        """Should find industry by partial name match."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        rule = populated_dna_loader.find_industry_for_niche("health")
        assert rule is not None

    def test_find_industry_no_match(self, populated_dna_loader):
        """Should return None for no matching industry."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        rule = populated_dna_loader.find_industry_for_niche("nonexistent_industry")
        assert rule is None
