"""Tests for validation gates, glossary, stats, singleton, and resolve_modules."""

import pytest
import threading

from src.core.dna_loader import (
    DNALoader, YAML_AVAILABLE, get_dna_loader,
)


# ============================================================
#  Validation Gate Tests
# ============================================================

class TestValidationGates:
    """Tests for validation gate checking."""

    def test_validate_code_no_secrets(self, populated_dna_loader):
        """Clean code should pass secret detection."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        code = 'def hello():\n    """Greet."""\n    return "hello"'
        result = populated_dna_loader.validate_code(code)
        assert "score" in result

    def test_validate_code_with_secrets(self, populated_dna_loader):
        """Code with hardcoded secrets should fail validation."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        code = 'password = "super_secret_password_123"'
        result = populated_dna_loader.validate_code(code)
        assert len(result["failed"]) > 0

    def test_validate_code_with_eval(self, populated_dna_loader):
        """Code with eval() should fail validation."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        code = 'result = eval(user_input)'
        result = populated_dna_loader.validate_code(code)
        assert len(result["failed"]) > 0 or len(result["warnings"]) > 0

    def test_get_domain_gates(self, populated_dna_loader):
        """Should retrieve domain-specific gates."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        gates = populated_dna_loader.get_domain_gates("healthcare")
        assert len(gates) > 0

    def test_get_domain_gates_nonexistent(self, populated_dna_loader):
        """Should return empty list for unknown domain."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        gates = populated_dna_loader.get_domain_gates("nonexistent")
        assert gates == []


# ============================================================
#  Glossary / Polish Tests
# ============================================================

class TestGlossaryPolish:
    """Tests for professional glossary text polishing."""

    def test_polish_text(self, populated_dna_loader):
        """Should transform technical terms to corporate language."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        result = populated_dna_loader.polish_text("We need to refactor the module")
        assert "optimize" in result.lower()

    def test_polish_error(self, populated_dna_loader):
        """Should transform error messages to professional wording."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        result = populated_dna_loader.polish_error("NullPointerException")
        assert result == "Unexpected value encountered"

    def test_polish_error_no_match(self, populated_dna_loader):
        """Should return original error message when no match."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        result = populated_dna_loader.polish_error("SomeUnknownError")
        assert result == "SomeUnknownError"

    def test_describe_feature(self, populated_dna_loader):
        """Should return marketing description for a feature."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        desc = populated_dna_loader.describe_feature("auto_scaling")
        assert "marketing" in desc
        assert desc["marketing"] == "Elastic Capacity"


# ============================================================
#  Stats Tests
# ============================================================

class TestDNALoaderStats:
    """Tests for DNALoader stats property."""

    def test_stats_structure(self, populated_dna_loader):
        """Stats should contain expected keys."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        stats = populated_dna_loader.stats
        assert "logic_modules" in stats
        assert "domain_rules" in stats
        assert "validation_gates" in stats
        assert "glossary_entries" in stats
        assert "yaml_available" in stats

    def test_stats_auto_loads(self, populated_dna_loader):
        """Stats should trigger auto-load if not loaded."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        assert not populated_dna_loader._loaded
        stats = populated_dna_loader.stats
        assert populated_dna_loader._loaded

    def test_stats_reports_yaml_availability(self, populated_dna_loader):
        """Stats should report YAML availability."""
        stats = populated_dna_loader.stats
        assert "yaml_available" in stats
        assert stats["yaml_available"] == YAML_AVAILABLE


# ============================================================
#  Singleton Tests
# ============================================================

class TestSingleton:
    """Tests for get_dna_loader singleton."""

    def test_singleton_returns_same_instance(self):
        """get_dna_loader should return the same instance."""
        import src.core.dna_loader as mod
        mod._dna_loader_instance = None
        loader1 = get_dna_loader()
        loader2 = get_dna_loader()
        assert loader1 is loader2
        # Clean up
        mod._dna_loader_instance = None

    def test_singleton_is_dna_loader_type(self):
        """Singleton should be a DNALoader instance."""
        import src.core.dna_loader as mod
        mod._dna_loader_instance = None
        loader = get_dna_loader()
        assert isinstance(loader, DNALoader)
        mod._dna_loader_instance = None

    def test_singleton_thread_safe(self):
        """Singleton should be thread-safe."""
        import src.core.dna_loader as mod
        mod._dna_loader_instance = None
        results = []
        def get_loader():
            results.append(get_dna_loader())
        threads = [threading.Thread(target=get_loader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # All should be the same instance
        assert all(r is results[0] for r in results)
        mod._dna_loader_instance = None


# ============================================================
#  resolve_modules_for_niche Tests
# ============================================================

class TestResolveModules:
    """Tests for resolve_modules_for_niche."""

    def test_resolve_known_blocks(self, populated_dna_loader):
        """Should resolve known template blocks to logic modules."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        modules = populated_dna_loader.resolve_modules_for_niche(
            "test_niche", ["jwt_auth"]
        )
        # jwt_auth maps to auth_jwt_standard, jwt_create, jwt_verify
        assert any(m.id == "auth_jwt_standard" for m in modules)

    def test_resolve_unknown_blocks(self, populated_dna_loader):
        """Should return empty for blocks with no module mapping."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        modules = populated_dna_loader.resolve_modules_for_niche(
            "test_niche", ["pdf_generator"]
        )
        # pdf_generator maps to empty list
        assert len(modules) == 0

    def test_resolve_multiple_blocks(self, populated_dna_loader):
        """Should resolve multiple blocks without duplicates."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        modules = populated_dna_loader.resolve_modules_for_niche(
            "test_niche", ["jwt_auth", "api_key_auth"]
        )
        # Both resolve modules; no duplicates
        ids = [m.id for m in modules]
        assert len(ids) == len(set(ids))
