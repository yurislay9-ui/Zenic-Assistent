"""
ZENIC-AGENTS - AppGenerator Types & Constants

Data classes and constants used across the app_gen_parts sub-modules.
"""

import os
import logging
from typing import Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# === Project Output Configuration ===
PROJECTS_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "projects")


@dataclass
class GeneratedProject:
    """Resultado de la generación de un proyecto."""
    name: str = ""
    template_type: str = ""
    path: str = ""
    files: List[str] = field(default_factory=list)
    main_file: str = ""
    endpoints: List[Dict[str, str]] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "pending"  # pending, generated, verified, failed
    error: str = ""
    generation_time_s: float = 0.0
