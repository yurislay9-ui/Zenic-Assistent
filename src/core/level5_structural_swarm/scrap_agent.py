"""
ZENIC-AGENTS - Smart Scraper Agent v16 (Pure Python)

Scraper Inteligente multi-fuente con urllib (sin httpx, sin requests).
Compatible con Android/Termux, zero dependencias externas.

Fuentes integradas:
1. GitHub Code Search    - Busca codigo real en repos publicos (con API key)
2. DevDocs               - Documentacion de lenguajes y APIs (0 registro)
3. IconStack             - Iconos para UIs generadas (0 registro)
4. Picsum.photos         - Imagenes aleatorias profesionales (0 registro)

Configuracion via .env (ver .env.example):
- GITHUB_TOKEN / GITHUB_API_KEY: Token de GitHub (5000 req/h vs 60 req/h)
- GITHUB_METRICS_ENABLED: Recopilar metricas de GitHub
- SCRAPER_PREFERRED_SOURCE: github | devdocs | iconstack | picsum | auto
- SCRAPER_TIMEOUT: Timeout global en segundos
- SCRAPER_MAX_CHARS: Maximo de caracteres por fuente

Arquitectura:
- smart_fetch(): Auto-selecciona la fuente segun tipo de consulta
- fetch_modern_code(): Backward-compatible con el pipeline original
- Cada fuente tiene su propio metodo fetch_xxx() independiente
- Todas las fuentes usan urllib puro (stdlib), sin dependencias
- Metricas de GitHub integradas (rate_limit, search_stats)
"""

# Imports preserved for test-patch compatibility (tests patch these paths)
import json
import time
import logging
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, Any

from src.core.env_loader import (
    load_env, get_env, get_env_int, get_env_bool,
    get_env_list, get_github_token, get_scraper_config,
)

logger = logging.getLogger(__name__)

# Facade: re-export all public symbols from the sub-package
from src.core.level5_structural_swarm.scrap_parts import GitHubScrapAgent, GitHubMetrics

__all__ = ["GitHubScrapAgent", "GitHubMetrics"]
