"""
Zenic-Agents Asistente - Blueprint Bootstrap (Phase 5)

Extracted from main_headless.py to keep it under 400 lines.
Initializes the Blueprint Registry at application startup,
loads from niches and certified directories, and wires
Blueprints into SNA and ActionDispatcher.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def init_blueprint_registry(
    project_root: str,
    sna_engine: Any = None,
) -> Optional[Any]:
    """Initialize the Blueprint Registry at application startup.

    Loads Blueprints from:
      1. Niche YAML templates (auto-converted)
      2. Certified Blueprint YAML/JSON files

    Wires Blueprints into:
      - SNA Engine (monitor thresholds)
      - ActionDispatcher (schema validation)

    Args:
        project_root: Absolute path to the project root directory.
        sna_engine: Optional SNAEngine instance for wiring monitors.

    Returns:
        BlueprintRegistry instance or None if initialization failed.
    """
    try:
        from src.core.blueprints import get_blueprint_registry
        registry = get_blueprint_registry()

        # Load from niches directory
        niches_dir = os.path.join(project_root, "src", "templates", "niches")
        if os.path.isdir(niches_dir):
            niche_count = registry.load_from_niches(niches_dir)
            logger.info(
                "Blueprints: Loaded %d Blueprints from niches", niche_count,
            )

        # Load from dedicated blueprints directory (if exists)
        bp_dir = os.path.join(project_root, "src", "templates", "blueprints")
        if os.path.isdir(bp_dir):
            bp_count = registry.load_from_directory(bp_dir)
            logger.info(
                "Blueprints: Loaded %d certified Blueprints", bp_count,
            )

        # Wire Blueprint into ActionDispatcher
        if registry.list_all():
            _wire_dispatcher(registry)

            # Wire Blueprint monitors into SNA
            if sna_engine:
                _wire_sna_monitors(registry, sna_engine)

        logger.info(
            "Blueprints: %d registered, %d domains",
            len(registry.list_all()),
            len(registry.list_domains()),
        )
        return registry

    except Exception as e:
        logger.warning("Blueprints init failed: %s", e)
        return None


def _wire_dispatcher(registry: Any) -> None:
    """Wire Blueprint Registry into ActionDispatcher."""
    try:
        from src.core.executors.dispatch_action import get_default_dispatcher
        dispatcher = get_default_dispatcher()
        # ActionDispatcher already uses Blueprint for validation
        # set_blueprint_from_registry is called per-request
    except Exception:
        pass


def _wire_sna_monitors(registry: Any, sna_engine: Any) -> None:
    """Wire Blueprint monitor hooks into SNA ThresholdEngine."""
    for bp_name in registry.list_all():
        bp = registry.get(bp_name)
        if bp and bp.monitor_hooks:
            hooks_dict = bp.get_monitor_hooks_dict()
            loaded_thresholds = sna_engine.load_blueprint_thresholds(
                hooks_dict, blueprint_name=bp_name,
            )
            if loaded_thresholds:
                logger.info(
                    "Blueprints: %s → %d SNA thresholds loaded",
                    bp_name, loaded_thresholds,
                )
