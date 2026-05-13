"""
Shared imports, constants, and data classes for niche_scraper_parts.
"""

import os
import json
import time
import logging
import threading
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger(__name__)

# === Evolution DB ===
EVOLUTION_DB = os.path.join(
    os.path.expanduser("~"), ".zenic_agents", "db", "niche_evolution.sqlite"
)


@dataclass
class EvolutionEntry:
    """Registro de una mutación en un nicho."""
    niche_name: str
    mutation_type: str  # "entity_added", "field_added", "block_added", "pattern_updated"
    description: str
    source_repo: str
    timestamp: float = 0.0
    old_value: str = ""
    new_value: str = ""
    approved: bool = True  # Auto-approved by default

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
