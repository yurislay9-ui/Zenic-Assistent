"""Tests for SmartMemory initialization, client ID, and working memory."""

import sqlite3

from src.core.smart_memory import (
    SmartMemory, MAX_WORKING_ENTRIES,
)


# ============================================================
#  Initialization Tests
# ============================================================

class TestInitialization:
    """Tests for SmartMemory initialization."""

    def test_session_id_generated(self, memory):
        """Session ID should be an 8-char hex string."""
        assert len(memory._session_id) == 8
        assert all(c in "0123456789abcdef" for c in memory._session_id)

    def test_default_client_id(self, memory):
        """Default client_id should be 'default'."""
        assert memory._client_id == "default"

    def test_working_memory_empty(self, memory):
        """Working memory should start empty."""
        assert len(memory._working_memory) == 0

    def test_db_tables_created(self, memory, temp_db):
        """All required DB tables should be created on init."""
        with sqlite3.connect(temp_db) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        assert "semantic_cache" in tables, f"semantic_cache not in {tables}"
        assert "long_term_memory" in tables, f"long_term_memory not in {tables}"
        assert "episodic_memory" in tables, f"episodic_memory not in {tables}"
        assert "procedural_memory" in tables, f"procedural_memory not in {tables}"
        assert "project_memory" in tables, f"project_memory not in {tables}"

    def test_semantic_engine_none(self, memory):
        """Semantic engine should be None when not provided."""
        assert memory._semantic is None


# ============================================================
#  Client ID Tests
# ============================================================

class TestClientId:
    """Tests for multi-client isolation."""

    def test_set_valid_client_id(self, memory):
        """Should accept valid client_id strings."""
        memory.set_client_id("client_abc")
        assert memory._client_id == "client_abc"

    def test_set_empty_client_id_raises(self, memory):
        """Should raise ValueError for empty client_id."""
        import pytest
        with pytest.raises(ValueError):
            memory.set_client_id("")

    def test_set_nonstring_client_id_raises(self, memory):
        """Should raise ValueError for non-string client_id."""
        import pytest
        with pytest.raises(ValueError):
            memory.set_client_id(123)

    def test_set_whitespace_client_id_raises(self, memory):
        """Should raise ValueError for whitespace-only client_id."""
        import pytest
        with pytest.raises(ValueError):
            memory.set_client_id("   ")


# ============================================================
#  Working Memory Tests
# ============================================================

class TestWorkingMemory:
    """Tests for working memory (short-term context)."""

    def test_add_working_entry(self, memory):
        """Should add entry to working memory."""
        memory.add_working("test query", "test response", operation="CREATE")
        assert len(memory._working_memory) == 1
        assert memory._working_memory[0].query == "test query"

    def test_working_context_format(self, memory):
        """get_working_context should return formatted string."""
        memory.add_working("q1", "r1", operation="CREATE", goal="FEATURE_ADD")
        ctx = memory.get_working_context()
        assert "Previous context:" in ctx
        assert "CREATE" in ctx

    def test_working_context_empty(self, memory):
        """Should return empty string when no entries."""
        assert memory.get_working_context() == ""

    def test_eviction_on_overflow(self, memory):
        """Should evict lowest importance entry when over MAX_WORKING_ENTRIES."""
        for i in range(MAX_WORKING_ENTRIES + 5):
            memory.add_working(f"q{i}", f"r{i}", importance=0.1 + i * 0.01)
        assert len(memory._working_memory) <= MAX_WORKING_ENTRIES

    def test_get_recent_operations(self, memory):
        """Should return last N operations."""
        for op in ["CREATE", "REFACTOR", "DEBUG"]:
            memory.add_working("q", "r", operation=op)
        recent = memory.get_recent_operations(2)
        assert recent == ["REFACTOR", "DEBUG"]
