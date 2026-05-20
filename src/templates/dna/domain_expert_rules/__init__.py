"""Domain Expert Rules — Modular YAML loader.

Industry-specific mandatory rules are split across sub-files for maintainability.
Use load_all_industries() to get the assembled data.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


_DIR = Path(__file__).parent


def load_all_industries() -> dict[str, Any]:
    """Load and merge all domain expert rule YAML fragments.

    Returns a dict with key 'industries' containing the full list of industry
    definitions, identical to loading the original single-file domain_expert_rules.yaml.
    """
    industries: list[dict[str, Any]] = []
    for fragment in sorted(_DIR.glob("_*.yaml")):
        data = yaml.safe_load(fragment.read_text(encoding="utf-8"))
        industries.extend(data.get("industries", []))
    return {"industries": industries}
