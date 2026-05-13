"""
Tests for EnvLoader module.

Tests unitarios para el cargador de variables de entorno (.env):
- _parse_env_line
- get_github_token
- get_env_bool / get_env_int / get_env_list
- get_scraper_config
"""

import os
import unittest
from unittest.mock import patch


class TestEnvLoader(unittest.TestCase):
    """Tests para el cargador de variables de entorno (.env)."""

    def test_parse_env_line_simple(self):
        """Test: parsea linea KEY=VALUE simple."""
        from src.core.env_loader import _parse_env_line
        result = _parse_env_line("GITHUB_TOKEN=ghp_abc123")
        self.assertEqual(result, ("GITHUB_TOKEN", "ghp_abc123"))

    def test_parse_env_line_quoted(self):
        """Test: parsea linea con comillas dobles."""
        from src.core.env_loader import _parse_env_line
        result = _parse_env_line('GITHUB_TOKEN="ghp_abc with spaces"')
        self.assertEqual(result, ("GITHUB_TOKEN", "ghp_abc with spaces"))

    def test_parse_env_line_single_quoted(self):
        """Test: parsea linea con comillas simples."""
        from src.core.env_loader import _parse_env_line
        result = _parse_env_line("GITHUB_TOKEN='ghp_single_quotes'")
        self.assertEqual(result, ("GITHUB_TOKEN", "ghp_single_quotes"))

    def test_parse_env_line_comment(self):
        """Test: ignora comentarios."""
        from src.core.env_loader import _parse_env_line
        result = _parse_env_line("# This is a comment")
        self.assertIsNone(result)

    def test_parse_env_line_empty(self):
        """Test: ignora lineas vacias."""
        from src.core.env_loader import _parse_env_line
        result = _parse_env_line("")
        self.assertIsNone(result)

    def test_parse_env_line_no_equals(self):
        """Test: ignora lineas sin =."""
        from src.core.env_loader import _parse_env_line
        result = _parse_env_line("NO_EQUALS_HERE")
        self.assertIsNone(result)

    def test_parse_env_line_value_with_equals(self):
        """Test: parsea valor que contiene = (separar solo en el primero)."""
        from src.core.env_loader import _parse_env_line
        result = _parse_env_line("KEY=value=with=equals")
        self.assertEqual(result, ("KEY", "value=with=equals"))

    def test_get_github_token_primary(self):
        """Test: GITHUB_TOKEN tiene prioridad sobre GITHUB_API_KEY."""
        from src.core.env_loader import get_github_token, _loaded
        import src.core.env_loader as env_mod

        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "primary_token",
            "GITHUB_API_KEY": "fallback_token",
        }, clear=False):
            result = get_github_token()
            self.assertEqual(result, "primary_token")

    def test_get_github_token_fallback(self):
        """Test: usa GITHUB_API_KEY si no hay GITHUB_TOKEN."""
        from src.core.env_loader import get_github_token
        import src.core.env_loader as env_mod

        with patch.dict(os.environ, {
            "GITHUB_API_KEY": "fallback_token",
        }, clear=False):
            os.environ.pop("GITHUB_TOKEN", None)
            result = get_github_token()
            self.assertEqual(result, "fallback_token")

    def test_get_github_token_empty(self):
        """Test: retorna vacio si no hay token."""
        from src.core.env_loader import get_github_token
        import src.core.env_loader as env_mod

        with patch.dict(os.environ, {}, clear=True):
            result = get_github_token()
            self.assertEqual(result, "")

    def test_get_env_bool_truthy(self):
        """Test: valores truthy para booleanos."""
        from src.core.env_loader import get_env_bool
        import src.core.env_loader as env_mod

        for val in ("true", "yes", "1", "on"):
            with patch.dict(os.environ, {"TEST_BOOL": val}, clear=False):
                result = get_env_bool("TEST_BOOL")
                self.assertTrue(result, f"Expected True for '{val}'")

    def test_get_env_bool_falsy(self):
        """Test: valores falsy para booleanos."""
        from src.core.env_loader import get_env_bool
        import src.core.env_loader as env_mod

        for val in ("false", "no", "0", "off"):
            with patch.dict(os.environ, {"TEST_BOOL": val}, clear=False):
                result = get_env_bool("TEST_BOOL")
                self.assertFalse(result, f"Expected False for '{val}'")

    def test_get_env_int(self):
        """Test: parsea enteros correctamente."""
        from src.core.env_loader import get_env_int
        import src.core.env_loader as env_mod

        with patch.dict(os.environ, {"TEST_INT": "42"}, clear=False):
            result = get_env_int("TEST_INT")
            self.assertEqual(result, 42)

    def test_get_env_int_default(self):
        """Test: retorna default si no existe o es invalido."""
        from src.core.env_loader import get_env_int
        import src.core.env_loader as env_mod

        with patch.dict(os.environ, {}, clear=True):
            result = get_env_int("NONEXISTENT_INT", default=99)
            self.assertEqual(result, 99)

    def test_get_env_list(self):
        """Test: parsea lista separada por comas."""
        from src.core.env_loader import get_env_list
        import src.core.env_loader as env_mod

        with patch.dict(os.environ, {"TEST_LIST": "a, b, c"}, clear=False):
            result = get_env_list("TEST_LIST")
            self.assertEqual(result, ["a", "b", "c"])

    def test_get_scraper_config_defaults(self):
        """Test: configuracion por defecto del scraper."""
        from src.core.env_loader import get_scraper_config
        import src.core.env_loader as env_mod

        with patch.dict(os.environ, {}, clear=True):
            config = get_scraper_config()
            self.assertEqual(config["timeout"], 10)
            self.assertEqual(config["max_retries"], 2)
            self.assertEqual(config["max_chars"], 2000)
            self.assertEqual(config["preferred_source"], "auto")
            self.assertEqual(config["github_token"], "")
            self.assertEqual(config["devdocs_url"], "https://devdocs.io")
            self.assertEqual(config["iconstack_url"], "https://icon-icons.com")
            self.assertEqual(config["picsum_url"], "https://picsum.photos")
            self.assertEqual(config["picsum_width"], 800)
            self.assertEqual(config["picsum_height"], 600)

    def test_get_scraper_config_custom(self):
        """Test: configuracion custom desde entorno."""
        from src.core.env_loader import get_scraper_config
        import src.core.env_loader as env_mod

        with patch.dict(os.environ, {
            "SCRAPER_TIMEOUT": "15",
            "SCRAPER_MAX_CHARS": "3000",
            "SCRAPER_PREFERRED_SOURCE": "devdocs",
            "GITHUB_TOKEN": "ghp_test123",
        }, clear=False):
            config = get_scraper_config()
            self.assertEqual(config["timeout"], 15)
            self.assertEqual(config["max_chars"], 3000)
            self.assertEqual(config["preferred_source"], "devdocs")
            self.assertEqual(config["github_token"], "ghp_test123")
