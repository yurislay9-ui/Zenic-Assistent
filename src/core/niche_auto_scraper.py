"""
ZENIC-AGENTS - NicheAutoScraper (Facade)

Thin facade — all logic lives in niche_scraper_parts/.
"""

from .niche_scraper_parts import *  # noqa: F401,F403
from .niche_scraper_parts import (
    EvolutionEntry, TrendingAnalyzer, NicheAutoUpdater, NicheCronScheduler,
)

__all__ = [
    "EVOLUTION_DB",
    "YAML_AVAILABLE",
    "EvolutionEntry",
    "TrendingAnalyzer",
    "NicheAutoUpdater",
    "NicheCronScheduler",
]
