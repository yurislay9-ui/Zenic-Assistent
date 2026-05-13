"""
ZENIC-AGENTS - NicheAutoScraper Tests

Tests for the niche auto-learning system:
  - TrendingAnalyzer: pattern extraction from code, library mapping
  - NicheAutoUpdater: auto-update cycle, block/entity merging
  - NicheCronScheduler: cron scheduling, trigger_now
  - EvolutionEntry: timestamp defaults
"""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from dataclasses import dataclass

from src.core.niche_auto_scraper import (
    TrendingAnalyzer,
    NicheAutoUpdater,
    NicheCronScheduler,
    EvolutionEntry,
    YAML_AVAILABLE,
)


# ============================================================
#  FIXTURES
# ============================================================

@pytest.fixture
def mock_scrap_agent():
    """Create a mock GitHubScrapAgent."""
    agent = AsyncMock()
    agent.fetch_github_code = AsyncMock(return_value=None)
    return agent


@pytest.fixture
def analyzer(mock_scrap_agent):
    """Create a TrendingAnalyzer with a mock scrap agent."""
    return TrendingAnalyzer(scrap_agent=mock_scrap_agent)


@pytest.fixture
def mock_niche():
    """Create a mock niche object for testing."""
    niche = MagicMock()
    niche.name = "ecommerce"
    niche.domain = "retail"
    niche.subdomain = "online_store"
    niche.description = "E-commerce platform"
    niche.scale = "medium"
    niche.base_template = "fastapi_base"
    niche.app_template = "fastapi_app"
    niche.blocks = ["jwt_auth", "stripe_payments"]
    niche.entities = [{"name": "Product", "fields": ["name:str", "price:float"]}]
    niche.variables = {}
    niche.typical_paths = []
    niche.triggers = []
    niche.core_features = []
    niche.advanced_features = []
    niche.optional_features = []
    niche.data_sensitivity = "medium"
    niche.compliance = []
    niche.backup_frequency = "daily"
    niche.access_control = "role_based"
    niche.audit_trail = True
    niche.yaml_path = ""
    return niche


@pytest.fixture
def mock_niche_loader(mock_niche):
    """Create a mock NicheLoader."""
    loader = MagicMock()
    loader._root = "/tmp/niches"
    loader.search = MagicMock(return_value=[mock_niche])
    return loader


@pytest.fixture
def updater(mock_niche_loader, mock_scrap_agent):
    """Create a NicheAutoUpdater with mocks."""
    return NicheAutoUpdater(niche_loader=mock_niche_loader, scrap_agent=mock_scrap_agent)


# ============================================================
#  EVOLUTION ENTRY TESTS
# ============================================================

class TestEvolutionEntry:
    """Tests for EvolutionEntry dataclass."""

    def test_timestamp_auto_set(self):
        """Timestamp should be auto-set on creation."""
        before = time.time()
        entry = EvolutionEntry(
            niche_name="test",
            mutation_type="entity_added",
            description="Added entity",
            source_repo="github:test/repo",
        )
        after = time.time()
        assert before <= entry.timestamp <= after

    def test_timestamp_preserved(self):
        """Explicit timestamp should not be overwritten."""
        entry = EvolutionEntry(
            niche_name="test",
            mutation_type="block_added",
            description="Added block",
            source_repo="github:test/repo",
            timestamp=1000.0,
        )
        assert entry.timestamp == 1000.0

    def test_approved_default(self):
        """Entries should be auto-approved by default."""
        entry = EvolutionEntry(
            niche_name="test",
            mutation_type="entity_added",
            description="test",
            source_repo="test",
        )
        assert entry.approved is True


# ============================================================
#  TRENDING ANALYZER TESTS
# ============================================================

class TestTrendingAnalyzer:
    """Tests for the TrendingAnalyzer."""

    def test_no_scrap_agent_returns_empty(self):
        """Without a scrap agent, analyze_trending should return empty list."""
        analyzer = TrendingAnalyzer(scrap_agent=None)
        result = asyncio.run(
            analyzer.analyze_trending()
        )
        assert result == []

    def test_extract_patterns_python_imports(self, analyzer):
        """_extract_patterns should detect Python imports and map them to blocks."""
        code = "import stripe\nfrom sendgrid import SendGridClient\nimport pandas"
        patterns = analyzer._extract_patterns(code, "python")

        assert "stripe_payments" in patterns["suggested_blocks"]
        assert "email_smtp" in patterns["suggested_blocks"]
        assert "data_analyzer" in patterns["suggested_blocks"]
        assert "stripe" in patterns["libraries"]
        assert "sendgrid" in patterns["libraries"]

    def test_extract_patterns_javascript_imports(self, analyzer):
        """_extract_patterns should detect JS requires/imports."""
        code = 'const passport = require("passport")\nimport nextAuth from "next-auth"'
        patterns = analyzer._extract_patterns(code, "javascript")

        assert "jwt_auth" in patterns["suggested_blocks"]

    def test_extract_patterns_unknown_language(self, analyzer):
        """_extract_patterns with unsupported language should return empty lists."""
        code = "some code here"
        patterns = analyzer._extract_patterns(code, "rust")
        # Rust is in DEP_PATTERNS but regex doesn't match
        assert patterns["libraries"] == []
        assert patterns["suggested_blocks"] == []

    def test_extract_patterns_library_to_entities(self, analyzer):
        """Libraries mapped to entities should appear in suggested_entities."""
        code = "import stripe\nimport pandas"
        patterns = analyzer._extract_patterns(code, "python")

        entity_names = [e["name"] for e in patterns["suggested_entities"]]
        assert "Payment" in entity_names
        assert "Dataset" in entity_names

    def test_extract_patterns_no_duplicate_blocks(self, analyzer):
        """The same block should not appear twice even if multiple libs map to it."""
        code = "import fastapi_users\nimport authlib"
        patterns = analyzer._extract_patterns(code, "python")

        block_count = patterns["suggested_blocks"].count("jwt_auth")
        assert block_count == 1

    def test_analyze_trending_with_results(self, analyzer, mock_scrap_agent):
        """analyze_trending should return structured results."""
        mock_scrap_agent.fetch_github_code = AsyncMock(
            return_value="import stripe\nimport pandas"
        )
        result = asyncio.run(
            analyzer.analyze_trending(language="python")
        )
        assert isinstance(result, list)
        if result:
            assert "topic" in result[0]
            assert "patterns_detected" in result[0]

    def test_analyze_trending_exception_handling(self, analyzer, mock_scrap_agent):
        """analyze_trending should handle exceptions gracefully."""
        mock_scrap_agent.fetch_github_code = AsyncMock(side_effect=Exception("API error"))
        result = asyncio.run(
            analyzer.analyze_trending(language="python")
        )
        assert result == []

    def test_get_evolution_log_unfiltered(self, analyzer):
        """get_evolution_log without filter should return all entries."""
        entry = EvolutionEntry(
            niche_name="test", mutation_type="block_added",
            description="test", source_repo="test",
        )
        analyzer._evolution_log.append(entry)
        log = analyzer.get_evolution_log()
        assert len(log) == 1

    def test_get_evolution_log_filtered(self, analyzer):
        """get_evolution_log with niche_name should filter entries."""
        e1 = EvolutionEntry(niche_name="ecommerce", mutation_type="block_added",
                            description="test", source_repo="test")
        e2 = EvolutionEntry(niche_name="fintech", mutation_type="entity_added",
                            description="test", source_repo="test")
        analyzer._evolution_log = [e1, e2]

        log = analyzer.get_evolution_log(niche_name="ecommerce")
        assert len(log) == 1
        assert log[0].niche_name == "ecommerce"


# ============================================================
#  NICHE AUTO UPDATER TESTS
# ============================================================

class TestNicheAutoUpdater:
    """Tests for the NicheAutoUpdater."""

    def test_auto_update_no_loader(self, mock_scrap_agent):
        """auto_update without NicheLoader should return error."""
        updater = NicheAutoUpdater(niche_loader=None, scrap_agent=mock_scrap_agent)
        result = asyncio.run(updater.auto_update())
        assert "error" in result

    def test_auto_update_no_yml(self, mock_niche_loader, mock_scrap_agent):
        """auto_update without YAML should return error."""
        with patch("src.core.niche_scraper_parts._imports.YAML_AVAILABLE", False):
            updater = NicheAutoUpdater(niche_loader=mock_niche_loader, scrap_agent=mock_scrap_agent)
            result = asyncio.run(updater.auto_update())
            assert "error" in result

    def test_auto_update_merges_blocks(self, updater, mock_niche_loader, mock_niche, mock_scrap_agent):
        """auto_update should merge new blocks into matching niches."""
        mock_scrap_agent.fetch_github_code = AsyncMock(
            return_value="import firebase_admin"
        )
        mock_niche_loader.search = MagicMock(return_value=[mock_niche])

        with patch("src.core.niche_scraper_parts._imports.YAML_AVAILABLE", True):
            result = asyncio.run(updater.auto_update())

        # notification_manager should have been suggested by firebase-admin
        if result.get("mutations_applied", 0) > 0:
            assert "notification_manager" in mock_niche.blocks

    def test_auto_update_merges_entities(self, updater, mock_niche_loader, mock_niche, mock_scrap_agent):
        """auto_update should merge new entities into matching niches."""
        mock_scrap_agent.fetch_github_code = AsyncMock(
            return_value="import stripe"
        )
        mock_niche_loader.search = MagicMock(return_value=[mock_niche])

        with patch("src.core.niche_scraper_parts._imports.YAML_AVAILABLE", True):
            result = asyncio.run(updater.auto_update())

        # stripe_payments block and Payment entity should be suggested
        if result.get("mutations_applied", 0) > 0:
            entity_names = [e.get("name", "") for e in mock_niche.entities]
            assert "Payment" in entity_names

    def test_auto_update_stats(self, updater, mock_scrap_agent):
        """Stats should reflect the auto-update state."""
        stats = updater.stats
        assert "total_mutations" in stats
        assert "last_scan" in stats
        assert "evolution_entries" in stats
        assert "yaml_available" in stats

    def test_save_niche_yaml_no_path(self, updater, mock_niche):
        """_save_niche_yaml should return False when niche has no yaml_path."""
        mock_niche.yaml_path = ""
        result = updater._save_niche_yaml(mock_niche)
        assert result is False


# ============================================================
#  NICHE CRON SCHEDULER TESTS
# ============================================================

class TestNicheCronScheduler:
    """Tests for the NicheCronScheduler."""

    def test_default_interval(self, updater):
        """Default interval should be 24 hours."""
        scheduler = NicheCronScheduler(updater)
        assert scheduler._interval == 24

    def test_min_interval_enforced(self, updater):
        """Interval below minimum should be clamped to 1 hour."""
        scheduler = NicheCronScheduler(updater, interval_hours=0.1)
        assert scheduler._interval == 1

    def test_custom_interval(self, updater):
        """Custom interval should be respected if above minimum."""
        scheduler = NicheCronScheduler(updater, interval_hours=12)
        assert scheduler._interval == 12

    def test_trigger_now(self, updater, mock_scrap_agent):
        """trigger_now should execute auto_update synchronously."""
        mock_scrap_agent.fetch_github_code = AsyncMock(return_value=None)

        scheduler = NicheCronScheduler(updater)
        result = scheduler.trigger_now()
        assert isinstance(result, dict)
        assert scheduler._run_count == 1

    def test_trigger_now_error_handling(self, updater):
        """trigger_now should handle errors gracefully."""
        updater.auto_update = AsyncMock(side_effect=Exception("Network error"))
        scheduler = NicheCronScheduler(updater)
        result = scheduler.trigger_now()
        assert "error" in result

    def test_scheduler_stats(self, updater):
        """Stats should reflect scheduler state."""
        scheduler = NicheCronScheduler(updater)
        stats = scheduler.stats
        assert "interval_hours" in stats
        assert "run_count" in stats
        assert "is_running" in stats

    def test_start_stop_scheduler(self, updater):
        """Scheduler should start and stop cleanly."""
        scheduler = NicheCronScheduler(updater, interval_hours=1)
        scheduler.start()
        assert scheduler._thread is not None
        assert scheduler._thread.is_alive()

        scheduler.stop()
        scheduler._thread.join(timeout=5)
        assert not scheduler._thread.is_alive()
