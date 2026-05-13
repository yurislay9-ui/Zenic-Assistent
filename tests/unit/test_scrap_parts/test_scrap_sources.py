"""
Tests for fetch_all_sources and smart_fetch auto-routing.

Tests para las funciones multi-fuente y auto-routing:
- fetch_all_sources (4 fuentes)
- SmartFetch con auto-routing
"""

import asyncio
import os
import unittest
from unittest.mock import patch, MagicMock, AsyncMock


class TestFetchAllSources(unittest.TestCase):
    """Tests para fetch_all_sources (4 fuentes)."""

    def setUp(self):
        """Configura el entorno para cada test."""
        import src.core.env_loader as env_mod

    def _make_scraper(self, env=None):
        """Helper: crea un scraper con entorno mockeado."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubScrapAgent
        default_env = {
            "SCRAPER_TIMEOUT": "10",
            "SCRAPER_MAX_RETRIES": "0",
            "SCRAPER_MAX_CHARS": "2000",
            "SCRAPER_PREFERRED_SOURCE": "auto",
            "GITHUB_METRICS_ENABLED": "true",
            "GITHUB_METRICS_COLLECT": "rate_limit,search_results,repo_stats",
        }
        if env:
            default_env.update(env)
        with patch.dict(os.environ, default_env, clear=False):
            return GitHubScrapAgent()

    def test_fetch_all_sources_tries_all_four(self):
        """Test: fetch_all_sources intenta las 4 fuentes."""
        scraper = self._make_scraper()

        scraper.fetch_github_code = AsyncMock(return_value="github_code")
        scraper.fetch_devdocs = AsyncMock(return_value="devdocs_content")
        scraper.fetch_iconstack = AsyncMock(return_value="iconstack_icons")
        scraper.fetch_picsum = AsyncMock(return_value="picsum_image")

        result = asyncio.run(
            scraper.fetch_all_sources("test query", "python")
        )

        self.assertEqual(result["_total_sources"], 4)
        self.assertEqual(result["_successful_sources"], 4)
        self.assertIn("github", result)
        self.assertIn("devdocs", result)
        self.assertIn("iconstack", result)
        self.assertIn("picsum", result)
        self.assertEqual(result["_sources_tried"], ["github", "devdocs", "iconstack", "picsum"])

    def test_fetch_all_sources_partial_failure(self):
        """Test: fetch_all_sources maneja fallos parciales."""
        scraper = self._make_scraper()

        scraper.fetch_github_code = AsyncMock(return_value="github_code")
        scraper.fetch_devdocs = AsyncMock(return_value="")
        scraper.fetch_iconstack = AsyncMock(side_effect=Exception("API down"))
        scraper.fetch_picsum = AsyncMock(return_value="picsum_image")

        result = asyncio.run(
            scraper.fetch_all_sources("test query", "python")
        )

        self.assertEqual(result["_total_sources"], 4)
        self.assertEqual(result["_successful_sources"], 2)
        self.assertIn("github", result)
        self.assertIn("picsum", result)
        self.assertNotIn("devdocs", result)
        self.assertNotIn("iconstack", result)

    def test_fetch_all_sources_all_fail(self):
        """Test: fetch_all_sources maneja fallo total."""
        scraper = self._make_scraper()

        scraper.fetch_github_code = AsyncMock(return_value="")
        scraper.fetch_devdocs = AsyncMock(return_value="")
        scraper.fetch_iconstack = AsyncMock(return_value="")
        scraper.fetch_picsum = AsyncMock(return_value="")

        result = asyncio.run(
            scraper.fetch_all_sources("nonexistent query", "python")
        )

        self.assertEqual(result["_total_sources"], 4)
        self.assertEqual(result["_successful_sources"], 0)
        self.assertIn("_metrics", result)


class TestSmartFetchAutoRouting(unittest.TestCase):
    """Tests para smart_fetch con auto-routing."""

    def setUp(self):
        """Configura el entorno para cada test."""
        import src.core.env_loader as env_mod

    def _make_scraper(self, env=None):
        """Helper: crea un scraper con entorno mockeado."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubScrapAgent
        default_env = {
            "SCRAPER_TIMEOUT": "10",
            "SCRAPER_MAX_RETRIES": "0",
            "SCRAPER_MAX_CHARS": "2000",
            "SCRAPER_PREFERRED_SOURCE": "auto",
            "GITHUB_METRICS_ENABLED": "true",
            "GITHUB_METRICS_COLLECT": "rate_limit,search_results,repo_stats",
        }
        if env:
            default_env.update(env)
        with patch.dict(os.environ, default_env, clear=False):
            return GitHubScrapAgent()

    def test_auto_route_to_github(self):
        """Test: auto-routing redirige a github para codigo."""
        scraper = self._make_scraper()
        scraper.fetch_github_code = AsyncMock(return_value="code_result")

        result = asyncio.run(
            scraper.smart_fetch("implement auth function example", "python", "auto")
        )
        self.assertEqual(result["source"], "github")

    def test_auto_route_to_devdocs(self):
        """Test: auto-routing redirige a devdocs para docs."""
        scraper = self._make_scraper()
        scraper.fetch_devdocs = AsyncMock(return_value="docs_result")

        result = asyncio.run(
            scraper.smart_fetch("python docs api reference syntax method", "python", "auto")
        )
        self.assertEqual(result["source"], "devdocs")

    def test_auto_route_to_iconstack(self):
        """Test: auto-routing redirige a iconstack para iconos."""
        scraper = self._make_scraper()
        scraper.fetch_iconstack = AsyncMock(return_value="icons_result")

        result = asyncio.run(
            scraper.smart_fetch("icon for login button", "", "auto")
        )
        self.assertEqual(result["source"], "iconstack")

    def test_auto_route_to_picsum(self):
        """Test: auto-routing redirige a picsum para imagenes."""
        scraper = self._make_scraper()
        scraper.fetch_picsum = AsyncMock(return_value="picsum_result")

        result = asyncio.run(
            scraper.smart_fetch("hero image for dashboard", "", "auto")
        )
        self.assertEqual(result["source"], "picsum")

    def test_force_source_github(self):
        """Test: forzar fuente github ignora auto-routing."""
        scraper = self._make_scraper()
        scraper.fetch_github_code = AsyncMock(return_value="github_code")

        result = asyncio.run(
            scraper.smart_fetch("icon for login", "", "github")
        )
        self.assertEqual(result["source"], "github")

    def test_force_source_picsum(self):
        """Test: forzar fuente picsum."""
        scraper = self._make_scraper()
        scraper.fetch_picsum = AsyncMock(return_value="picsum_result")

        result = asyncio.run(
            scraper.smart_fetch("auth function", "python", "picsum")
        )
        self.assertEqual(result["source"], "picsum")
