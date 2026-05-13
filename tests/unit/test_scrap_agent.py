"""
ZENIC-AGENTS v16 - Smart Scraper Agent Tests

Tests unitarios para el Scraper Inteligente multi-fuente:
- GitHubScrapAgent (auto-routing, smart_fetch, fetch_all_sources)
- GitHubMetrics (rate_limit, search_stats, repo_stats)
- Env Loader (load_env, get_env, get_github_token, get_scraper_config)
- Integracion de las 4 fuentes: GitHub, DevDocs, IconStack, Picsum

Modularized into test_scrap_parts/ sub-directory.
"""

# Re-export all test classes from sub-modules for backward compatibility
from .test_scrap_parts import *

# Re-export fixtures so they're available when running via this facade
from .test_scrap_parts.conftest import _prevent_env_reload
