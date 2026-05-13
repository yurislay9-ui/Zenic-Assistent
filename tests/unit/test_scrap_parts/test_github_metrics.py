"""
Tests for GitHubMetrics class.

Tests para la clase GitHubMetrics:
- rate_limit, search_stats, repo_stats
"""

import os
import unittest
from unittest.mock import patch


class TestGitHubMetrics(unittest.TestCase):
    """Tests para la clase GitHubMetrics."""

    def setUp(self):
        """Configura el entorno para cada test."""
        import src.core.env_loader as env_mod

    def test_metrics_init_defaults(self):
        """Test: inicializacion con defaults."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubMetrics

        with patch.dict(os.environ, {}, clear=True):
            metrics = GitHubMetrics()
            self.assertTrue(metrics.enabled)
            self.assertEqual(metrics._search_count, 0)
            self.assertEqual(metrics._search_results_total, 0)
            self.assertEqual(len(metrics._repos_seen), 0)

    def test_update_rate_limit(self):
        """Test: actualiza metricas de rate limit desde headers."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubMetrics

        with patch.dict(os.environ, {
            "GITHUB_METRICS_ENABLED": "true",
            "GITHUB_METRICS_COLLECT": "rate_limit",
        }, clear=False):
            metrics = GitHubMetrics()
            headers = {
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Limit": "5000",
                "X-RateLimit-Reset": "1700000000",
            }
            metrics.update_rate_limit(headers)
            self.assertEqual(metrics._rate_limit_remaining, 4999)
            self.assertEqual(metrics._rate_limit_limit, 5000)
            self.assertEqual(metrics._rate_limit_reset, 1700000000)

    def test_update_rate_limit_disabled(self):
        """Test: no actualiza si metrics esta deshabilitado."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubMetrics

        with patch.dict(os.environ, {
            "GITHUB_METRICS_ENABLED": "false",
        }, clear=False):
            metrics = GitHubMetrics()
            headers = {
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Limit": "5000",
            }
            metrics.update_rate_limit(headers)
            self.assertEqual(metrics._rate_limit_remaining, 0)

    def test_update_search_stats(self):
        """Test: actualiza estadisticas de busqueda."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubMetrics

        with patch.dict(os.environ, {
            "GITHUB_METRICS_ENABLED": "true",
            "GITHUB_METRICS_COLLECT": "search_results",
        }, clear=False):
            metrics = GitHubMetrics()
            metrics.update_search_stats(150, "test query")
            self.assertEqual(metrics._search_count, 1)
            self.assertEqual(metrics._search_results_total, 150)

    def test_update_repo_stats(self):
        """Test: actualiza estadisticas de repos."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubMetrics

        with patch.dict(os.environ, {
            "GITHUB_METRICS_ENABLED": "true",
            "GITHUB_METRICS_COLLECT": "repo_stats",
        }, clear=False):
            metrics = GitHubMetrics()
            metrics.update_repo_stats("user/repo1")
            metrics.update_repo_stats("user/repo2")
            metrics.update_repo_stats("user/repo1")  # Duplicado
            self.assertEqual(len(metrics._repos_seen), 2)

    def test_get_stats(self):
        """Test: retorna todas las metricas recopiladas."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubMetrics

        with patch.dict(os.environ, {
            "GITHUB_METRICS_ENABLED": "true",
            "GITHUB_METRICS_COLLECT": "rate_limit,search_results,repo_stats",
        }, clear=False):
            metrics = GitHubMetrics()
            metrics.update_rate_limit({
                "X-RateLimit-Remaining": "4500",
                "X-RateLimit-Limit": "5000",
                "X-RateLimit-Reset": "1700000000",
            })
            metrics.update_search_stats(100, "test")
            metrics.update_repo_stats("user/repo")

            stats = metrics.get_stats()
            self.assertIn("rate_limit", stats)
            self.assertIn("search", stats)
            self.assertIn("repos", stats)
            self.assertEqual(stats["rate_limit"]["remaining"], 4500)
            self.assertEqual(stats["search"]["queries_made"], 1)
            self.assertEqual(stats["repos"]["unique_repos_seen"], 1)
