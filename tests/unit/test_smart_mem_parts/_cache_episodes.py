"""Tests for semantic cache, episodic memory, procedural memory, and project memory."""

import sqlite3

from src.core.smart_memory import (
    SmartMemory, DB_PATH, IMPORTANCE_THRESHOLD,
)


# ============================================================
#  Semantic Cache Tests
# ============================================================

class TestSemanticCache:
    """Tests for semantic cache (exact + semantic matching)."""

    def test_save_and_check_cache_exact(self, memory):
        """Should retrieve from cache with exact hash match."""
        memory.save_to_cache("hello world", "Hello!", operation="GREET")
        result = memory.check_cache("hello world")
        assert result is not None
        assert result["source"] == "cache_exact"
        assert result["response"] == "Hello!"

    def test_cache_miss(self, memory):
        """Should return None for uncached queries."""
        result = memory.check_cache("uncached query")
        assert result is None

    def test_cache_case_insensitive(self, memory):
        """Should match regardless of case differences."""
        memory.save_to_cache("Hello World", "response")
        result = memory.check_cache("hello world")
        assert result is not None

    def test_high_importance_promotes_to_long_term(self, memory):
        """Entries with importance >= threshold should promote to long-term."""
        memory.save_to_cache("critical query", "critical response",
                             importance=IMPORTANCE_THRESHOLD)
        with sqlite3.connect(DB_PATH) as conn:
            count = conn.execute("SELECT COUNT(*) FROM long_term_memory").fetchone()[0]
        assert count >= 1

    def test_cache_semantic_match(self, memory_with_semantic):
        """Should retrieve from cache via semantic similarity."""
        memory_with_semantic.save_to_cache("authentication module", "auth code")
        result = memory_with_semantic.check_cache("auth module")
        # With mock similarity=0.9, should get a semantic match
        assert result is not None
        assert result["source"] == "cache_semantic"


# ============================================================
#  Episodic Memory Tests
# ============================================================

class TestEpisodicMemory:
    """Tests for episodic memory (event history)."""

    def test_save_and_find_by_type(self, memory):
        """Should save and retrieve episodes by event type."""
        memory.save_episode("app_generated", "Generated auth app",
                            importance=0.8)
        results = memory.find_episodes(event_type="app_generated")
        assert len(results) == 1
        assert results[0]["event_type"] == "app_generated"
        assert results[0]["description"] == "Generated auth app"

    def test_find_episodes_no_match(self, memory):
        """Should return empty list for non-matching event type."""
        memory.save_episode("app_generated", "test")
        results = memory.find_episodes(event_type="nonexistent")
        assert results == []

    def test_find_episodes_limit(self, memory):
        """Should respect the limit parameter."""
        for i in range(10):
            memory.save_episode("app_generated", f"app {i}")
        results = memory.find_episodes(event_type="app_generated", limit=3)
        assert len(results) <= 3

    def test_find_episodes_by_semantic_query(self, memory_with_semantic):
        """Should find episodes via semantic similarity query."""
        memory_with_semantic.save_episode("deployment", "Deployed to production")
        results = memory_with_semantic.find_episodes(query="production deploy")
        # With mock similarity=0.9, should find results
        assert len(results) >= 1


# ============================================================
#  Procedural Memory Tests
# ============================================================

class TestProceduralMemory:
    """Tests for procedural memory (learned patterns)."""

    def test_learn_and_find_pattern(self, memory):
        """Should learn a pattern and find it by type."""
        memory.learn_pattern("auth_jwt", "strategy", "JWT authentication pattern",
                             steps=["create token", "verify token"], success=True)
        results = memory.find_patterns(pattern_type="strategy")
        assert len(results) == 1
        assert results[0]["pattern_name"] == "auth_jwt"

    def test_learn_pattern_updates_success_rate(self, memory):
        """Should update success rate when pattern is learned again."""
        memory.learn_pattern("cache_pattern", "strategy", "Caching pattern",
                             success=True)
        memory.learn_pattern("cache_pattern", "strategy", "Caching pattern",
                             success=False)
        results = memory.find_patterns(pattern_type="strategy")
        assert len(results) == 1
        assert results[0]["success_rate"] == 0.5

    def test_find_patterns_min_success_rate(self, memory):
        """Should filter patterns by minimum success rate."""
        memory.learn_pattern("failing", "strategy", "Bad pattern", success=False)
        results = memory.find_patterns(min_success_rate=0.5)
        # failing pattern has 0% success rate
        assert not any(r["pattern_name"] == "failing" for r in results)

    def test_find_patterns_by_semantic_query(self, memory_with_semantic):
        """Should find patterns via semantic similarity query."""
        memory_with_semantic.learn_pattern("auth_pattern", "strategy",
                                           "Authentication pattern", success=True)
        results = memory_with_semantic.find_patterns(query="login auth")
        assert len(results) >= 1


# ============================================================
#  Project Memory Tests
# ============================================================

class TestProjectMemory:
    """Tests for project memory (project continuity)."""

    def test_save_and_get_project(self, memory):
        """Should save and retrieve project details."""
        memory.save_project("myapp", project_type="fastapi",
                            description="Auth service", status="active")
        proj = memory.get_project("myapp")
        assert proj is not None
        assert proj["project_name"] == "myapp"
        assert proj["project_type"] == "fastapi"

    def test_get_nonexistent_project(self, memory):
        """Should return None for non-existent project."""
        result = memory.get_project("nonexistent")
        assert result is None

    def test_update_existing_project(self, memory):
        """Should update an existing project instead of duplicating."""
        memory.save_project("myapp", project_type="flask", status="active")
        memory.save_project("myapp", project_type="fastapi", status="generated")
        proj = memory.get_project("myapp")
        assert proj["project_type"] == "fastapi"
        assert proj["status"] == "generated"

    def test_list_projects(self, memory):
        """Should list all projects."""
        memory.save_project("proj_a", project_type="flask")
        memory.save_project("proj_b", project_type="fastapi")
        projects = memory.list_projects()
        assert len(projects) == 2

    def test_list_projects_by_status(self, memory):
        """Should filter projects by status."""
        memory.save_project("proj_a", status="active")
        memory.save_project("proj_b", status="generated")
        active = memory.list_projects(status="active")
        assert len(active) == 1
        assert active[0]["project_name"] == "proj_a"
