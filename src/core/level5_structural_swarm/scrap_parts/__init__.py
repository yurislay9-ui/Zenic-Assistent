"""
ZENIC-AGENTS - Smart Scraper Agent v16 (Pure Python) - Sub-package

Scraper Inteligente multi-fuente con urllib (sin httpx, sin requests).
Compatible con Android/Termux, zero dependencias externas.

Fuentes integradas:
1. GitHub Code Search    - Busca codigo real en repos publicos (con API key)
2. DevDocs               - Documentacion de lenguajes y APIs (0 registro)
3. IconStack             - Iconos para UIs generadas (0 registro)
4. Picsum.photos         - Imagenes aleatorias profesionales (0 registro)
"""

from src.core.level5_structural_swarm.scrap_parts.metrics import GitHubMetrics
from src.core.level5_structural_swarm.scrap_parts.agent import GitHubScrapAgent

__all__ = ["GitHubScrapAgent", "GitHubMetrics"]
