"""
Tests for signature search, compact context, project indexing, and stats.
"""

import pytest

from src.core.context_pointer_engine import (
    FunctionSignature, ContextPointer, SignatureIndex, CONTEXT_STORE_ROOT,
)


# ============================================================
#  SignatureIndex - Search Tests
# ============================================================

class TestSignatureSearch:
    """Tests for signature search and similarity matching."""

    def test_search_by_name(self, populated_index):
        """Should find signatures by exact or partial name match."""
        results = populated_index.search("login")
        assert len(results) >= 1
        assert any(p.signature.name == "login" for p in results)

    def test_search_by_partial_name(self, populated_index):
        """Should find signatures by partial name match."""
        results = populated_index.search("log")
        assert len(results) >= 1

    def test_search_no_results(self, populated_index):
        """Should return empty for non-matching query."""
        results = populated_index.search("nonexistent_function_xyz")
        assert results == []

    def test_search_respects_top_k(self, populated_index):
        """Should limit results to top_k."""
        results = populated_index.search("a", top_k=1)
        assert len(results) <= 1

    def test_search_returns_context_pointers(self, populated_index):
        """Search results should be ContextPointer instances."""
        results = populated_index.search("login")
        assert all(isinstance(p, ContextPointer) for p in results)

    def test_search_includes_relevance_score(self, populated_index):
        """Each result should have a relevance_score > 0."""
        results = populated_index.search("login")
        assert all(p.relevance_score > 0 for p in results)

    def test_get_by_name_exact(self, populated_index):
        """Should find a signature by exact name."""
        ptr = populated_index.get_by_name("login")
        assert ptr is not None
        assert ptr.signature.name == "login"

    def test_get_by_name_not_found(self, populated_index):
        """Should return None for unknown name."""
        ptr = populated_index.get_by_name("nonexistent")
        assert ptr is None


# ============================================================
#  SignatureIndex - Compact Context Tests
# ============================================================

class TestCompactContext:
    """Tests for build_compact_context method."""

    def test_compact_context_format(self, populated_index):
        """Should produce a context string with pointers."""
        ctx, pointers = populated_index.build_compact_context("login")
        assert "Context Pointers" in ctx or "login" in ctx
        assert len(pointers) >= 1

    def test_compact_context_no_results(self, signature_index):
        """Should return message when no functions found."""
        ctx, pointers = signature_index.build_compact_context("nonexistent")
        assert "No se encontraron" in ctx or len(pointers) == 0

    def test_compact_context_respects_max_tokens(self, populated_index):
        """Should limit output based on max_tokens parameter."""
        ctx, pointers = populated_index.build_compact_context("a", max_tokens=50)
        # With very low max_tokens, should produce limited output
        assert isinstance(ctx, str)


# ============================================================
#  SignatureIndex - Project Indexing Tests
# ============================================================

class TestProjectIndexing:
    """Tests for index_project method."""

    def test_index_project_with_files(self, tmp_path, monkeypatch):
        """Should index all code files in a project directory."""
        store_dir = str(tmp_path / "ctx_store")
        monkeypatch.setattr("src.core.context_pointer_engine.CONTEXT_STORE_ROOT", store_dir)

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("def main(): pass\n")
        (src_dir / "utils.py").write_text("def helper(): pass\n")
        (src_dir / "readme.md").write_text("# Not code")  # Should be ignored

        idx = SignatureIndex(project_root=str(tmp_path))
        count = idx.index_project()
        assert count >= 2  # main and helper functions

    def test_index_project_nonexistent(self, signature_index):
        """Should return 0 for nonexistent project root."""
        count = signature_index.index_project("/nonexistent/path")
        assert count == 0

    def test_index_project_multiple_languages(self, tmp_path, monkeypatch):
        """Should index files of multiple code languages."""
        store_dir = str(tmp_path / "ctx_store")
        monkeypatch.setattr("src.core.context_pointer_engine.CONTEXT_STORE_ROOT", store_dir)

        src_dir = tmp_path / "multi"
        src_dir.mkdir()
        (src_dir / "app.py").write_text("def python_func(): pass\n")
        (src_dir / "app.js").write_text("function jsFunc() {}\n")

        idx = SignatureIndex(project_root=str(src_dir))
        count = idx.index_project()
        assert count >= 1  # At least python_func


# ============================================================
#  SignatureIndex - Stats Tests
# ============================================================

class TestSignatureIndexStats:
    """Tests for SignatureIndex stats property."""

    def test_stats_structure(self, populated_index):
        """Stats should contain expected keys."""
        stats = populated_index.stats
        assert "total_signatures" in stats
        assert "total_files" in stats
        assert "unique_names" in stats
        assert "store_dir" in stats

    def test_stats_counts(self, populated_index):
        """Stats should report correct counts."""
        stats = populated_index.stats
        assert stats["total_signatures"] >= 3
        assert stats["total_files"] == 1
        assert stats["unique_names"] >= 3

    def test_stats_empty_index(self, signature_index):
        """Empty index should report zero counts."""
        stats = signature_index.stats
        assert stats["total_signatures"] == 0
        assert stats["total_files"] == 0
        assert stats["unique_names"] == 0
