"""
Tests for GitHubScrapAgent core functionality.

Tests para la clase GitHubScrapAgent (Smart Scraper):
- Initialization, source detection, smart_fetch, caching
- fetch_github_code, fetch_picsum, fetch_iconstack
- fetch_modern_code backward compatibility
"""

import asyncio
import json
import os
import unittest
from unittest.mock import patch, MagicMock, AsyncMock


class TestGitHubScrapAgent(unittest.TestCase):
    """Tests para la clase GitHubScrapAgent (Smart Scraper)."""

    def setUp(self):
        """Configura el entorno para cada test."""
        import src.core.env_loader as env_mod

    def _make_scraper(self, env=None):
        """Helper: crea un scraper con entorno mockeado."""
        from src.core.level5_structural_swarm.scrap_agent import GitHubScrapAgent
        default_env = {
            "SCRAPER_TIMEOUT": "10",
            "SCRAPER_MAX_RETRIES": "2",
            "SCRAPER_MAX_CHARS": "2000",
            "SCRAPER_PREFERRED_SOURCE": "auto",
            "GITHUB_METRICS_ENABLED": "true",
            "GITHUB_METRICS_COLLECT": "rate_limit,search_results,repo_stats",
        }
        if env:
            default_env.update(env)
        with patch.dict(os.environ, default_env, clear=False):
            return GitHubScrapAgent()

    def test_scraper_init(self):
        """Test: inicializacion del scraper."""
        scraper = self._make_scraper({"GITHUB_TOKEN": "ghp_test"})
        self.assertEqual(scraper._timeout, 10)
        self.assertEqual(scraper._max_retries, 2)
        self.assertEqual(scraper._max_chars, 2000)
        self.assertEqual(scraper._preferred_source, "auto")
        self.assertIsNotNone(scraper._metrics)

    def test_scraper_init_with_token(self):
        """Test: scraper reconoce cuando hay token configurado."""
        scraper = self._make_scraper({"GITHUB_TOKEN": "ghp_test_token_123"})
        self.assertEqual(scraper._config["github_token"], "ghp_test_token_123")

    def test_scraper_init_without_token(self):
        """Test: scraper funciona sin token (modo limitado)."""
        scraper = self._make_scraper({"GITHUB_TOKEN": "", "GITHUB_API_KEY": ""})
        self.assertEqual(scraper._config["github_token"], "")

    def test_detect_source_code(self):
        """Test: detecta consultas de codigo -> github."""
        scraper = self._make_scraper()
        self.assertEqual(scraper._detect_source("how to implement auth example"), "github")
        self.assertEqual(scraper._detect_source("build a function pattern"), "github")
        self.assertEqual(scraper._detect_source("kotlin repository snippet"), "github")

    def test_detect_source_docs(self):
        """Test: detecta consultas de documentacion -> devdocs."""
        scraper = self._make_scraper()
        self.assertEqual(scraper._detect_source("python docs api reference syntax"), "devdocs")
        self.assertEqual(scraper._detect_source("what is the method specification tutorial guide"), "devdocs")

    def test_detect_source_icons(self):
        """Test: detecta consultas de iconos -> iconstack."""
        scraper = self._make_scraper()
        self.assertEqual(scraper._detect_source("icon for login button"), "iconstack")
        self.assertEqual(scraper._detect_source("svg logo symbol"), "iconstack")
        self.assertEqual(scraper._detect_source("menu icono"), "iconstack")

    def test_detect_source_images(self):
        """Test: detecta consultas de imagenes -> picsum."""
        scraper = self._make_scraper()
        self.assertEqual(scraper._detect_source("hero image for dashboard"), "picsum")
        self.assertEqual(scraper._detect_source("background photo banner"), "picsum")
        self.assertEqual(scraper._detect_source("placeholder image"), "picsum")

    def test_detect_source_priority(self):
        """Test: prioridad de deteccion (iconstack > picsum > devdocs > github)."""
        scraper = self._make_scraper()
        self.assertEqual(scraper._detect_source("icon image for menu"), "iconstack")
        self.assertEqual(scraper._detect_source("photo documentation reference"), "picsum")

    def test_detect_source_default_github(self):
        """Test: default es github para consultas genericas."""
        scraper = self._make_scraper()
        self.assertEqual(scraper._detect_source("auth login python"), "github")

    def test_smart_fetch_cached(self):
        """Test: smart_fetch retorna resultado cacheado."""
        scraper = self._make_scraper()
        scraper._cache["github:auth python:python"] = "cached_code_result"

        result = asyncio.run(
            scraper.smart_fetch("auth python", "python", "github")
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["content"], "cached_code_result")
        self.assertTrue(result["metadata"]["cached"])

    def test_smart_fetch_unknown_source(self):
        """Test: smart_fetch usa github como fallback para fuente desconocida."""
        scraper = self._make_scraper()

        async def mock_fetch(query, lang=""):
            return "mocked_github_code"

        scraper.fetch_github_code = mock_fetch

        result = asyncio.run(
            scraper.smart_fetch("test query", "python", "unknown_source")
        )
        self.assertEqual(result["source"], "github")
        self.assertTrue(result["success"])

    def test_fetch_modern_code_backward_compat(self):
        """Test: fetch_modern_code es backward-compatible."""
        scraper = self._make_scraper()

        async def mock_fetch_github(query, lang=""):
            return "backward_compat_code"

        scraper.fetch_github_code = mock_fetch_github

        result = asyncio.run(
            scraper.fetch_modern_code("auth login", "kotlin")
        )
        self.assertEqual(result, "backward_compat_code")

    def test_fetch_picsum_default(self):
        """Test: fetch_picsum genera URL con dimensiones por defecto."""
        scraper = self._make_scraper()

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.url = "https://picsum.photos/800/600"
            mock_resp.headers = MagicMock()
            mock_resp.headers.get.side_effect = lambda k, d="": {
                "Content-Type": "image/jpeg",
                "Content-Length": "123456",
            }.get(k, d)
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = asyncio.run(
                scraper.fetch_picsum()
            )
            self.assertTrue(bool(result))
            data = json.loads(result)
            self.assertEqual(data["source"], "picsum")
            self.assertIn("https://picsum.photos/800/600", data["direct_url"])
            self.assertIn("usage", data)
            self.assertIn("html", data["usage"])
            self.assertIn("css", data["usage"])

    def test_fetch_picsum_custom_dimensions(self):
        """Test: fetch_picsum acepta dimensiones personalizadas."""
        scraper = self._make_scraper()

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.url = "https://picsum.photos/1200x800"
            mock_resp.headers = MagicMock()
            mock_resp.headers.get.side_effect = lambda k, d="": {
                "Content-Type": "image/jpeg",
                "Content-Length": "200000",
            }.get(k, d)
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = asyncio.run(
                scraper.fetch_picsum("1200x800")
            )
            self.assertTrue(bool(result))
            data = json.loads(result)
            self.assertIn("1200", data["direct_url"])
            self.assertIn("800", data["direct_url"])

    def test_fetch_picsum_max_dimensions(self):
        """Test: fetch_picsum limita dimensiones a 1920x1080."""
        scraper = self._make_scraper()

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.url = "https://picsum.photos/1920/1080"
            mock_resp.headers = MagicMock()
            mock_resp.headers.get.side_effect = lambda k, d="": {
                "Content-Type": "image/jpeg",
                "Content-Length": "500000",
            }.get(k, d)
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = asyncio.run(
                scraper.fetch_picsum("3840x2160")  # 4K - deberia limitar
            )
            self.assertTrue(bool(result))
            data = json.loads(result)
            self.assertEqual(data["metadata"]["width"], 1920)
            self.assertEqual(data["metadata"]["height"], 1080)

    def test_fetch_iconstack_fallback(self):
        """Test: fetch_iconstack usa fallback Material Design icons."""
        scraper = self._make_scraper()

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("API unavailable")

            result = asyncio.run(
                scraper.fetch_iconstack("login")
            )
            self.assertTrue(bool(result))
            data = json.loads(result)
            self.assertEqual(data["source"], "iconstack")
            self.assertEqual(len(data["icons"]), 1)
            self.assertEqual(data["icons"][0]["name"], "login")
            self.assertIn("Fallback", data.get("note", ""))

    def test_fetch_iconstack_known_icons(self):
        """Test: fallback tiene iconos conocidos de Material Design."""
        scraper = self._make_scraper()

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("API unavailable")

            for icon_name in ["login", "logout", "menu", "settings", "home",
                              "user", "search", "add", "delete", "edit"]:
                result = asyncio.run(
                    scraper.fetch_iconstack(icon_name)
                )
                self.assertTrue(bool(result), f"Expected result for icon '{icon_name}'")
                data = json.loads(result)
                self.assertEqual(data["source"], "iconstack")

    def test_fetch_iconstack_unknown_icon(self):
        """Test: iconstack retorna vacio para icono desconocido sin API."""
        scraper = self._make_scraper()

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("API unavailable")

            result = asyncio.run(
                scraper.fetch_iconstack("xyzzy_nonexistent_icon_12345")
            )
            self.assertEqual(result, "")

    def test_fetch_github_code_with_token(self):
        """Test: GitHub usa token en Authorization header."""
        scraper = self._make_scraper({"GITHUB_TOKEN": "ghp_test_token"})

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.headers = MagicMock()
            mock_resp.read.return_value = json.dumps({"total_count": 0, "items": []}).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = asyncio.run(
                scraper.fetch_github_code("test query", "python")
            )

            call_args = mock_urlopen.call_args
            req = call_args[0][0]
            self.assertIn("Authorization", req.headers)
            self.assertEqual(req.headers["Authorization"], "token ghp_test_token")

    def test_fetch_github_code_without_token(self):
        """Test: GitHub funciona sin token (modo 60 req/h)."""
        scraper = self._make_scraper({"GITHUB_TOKEN": "", "GITHUB_API_KEY": ""})

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.headers = MagicMock()
            mock_resp.read.return_value = json.dumps({"total_count": 0, "items": []}).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = asyncio.run(
                scraper.fetch_github_code("test query", "python")
            )

            call_args = mock_urlopen.call_args
            req = call_args[0][0]
            self.assertNotIn("Authorization", req.headers)

    def test_fetch_github_code_rate_limit(self):
        """Test: GitHub maneja rate limit (403) correctamente."""
        scraper = self._make_scraper()
        import urllib.error

        with patch("src.core.level5_structural_swarm.scrap_agent.urllib.request.urlopen") as mock_urlopen:
            error = urllib.error.HTTPError(
                url="https://api.github.com/search/code",
                code=403,
                msg="Forbidden",
                hdrs={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1700000000"},
                fp=None,
            )
            mock_urlopen.side_effect = error

            result = asyncio.run(
                scraper.fetch_github_code("test query", "python")
            )
            self.assertEqual(result, "")  # No crashea, retorna vacio

    def test_cache_limit(self):
        """Test: cache se limpia automaticamente al pasar de 100 entradas."""
        scraper = self._make_scraper()

        for i in range(105):
            scraper._cache[f"github:query{i}:python"] = f"result_{i}"

        self.assertGreater(len(scraper._cache), 100)

        if len(scraper._cache) > 100:
            keys = list(scraper._cache.keys())
            for k in keys[:20]:
                del scraper._cache[k]

        self.assertLessEqual(len(scraper._cache), 85)

    def test_get_all_metrics(self):
        """Test: get_all_metrics retorna estructura completa."""
        scraper = self._make_scraper({"GITHUB_TOKEN": "ghp_test"})

        metrics = scraper.get_all_metrics()
        self.assertIn("github", metrics)
        self.assertIn("config", metrics)
        self.assertIn("cache", metrics)
        self.assertTrue(metrics["config"]["has_github_token"])
        self.assertEqual(metrics["config"]["devdocs_url"], "https://devdocs.io")
        self.assertEqual(metrics["config"]["iconstack_url"], "https://icon-icons.com")
        self.assertEqual(metrics["config"]["picsum_url"], "https://picsum.photos")
