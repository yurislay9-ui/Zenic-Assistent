"""Professional Glossary — Modular YAML loader.

Transformation rules are split across sub-files for maintainability.
Use load_all_rules() to get the assembled data.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


_DIR = Path(__file__).parent


def load_all_rules() -> dict[str, Any]:
    """Load and merge all professional glossary YAML fragments.

    Returns a dict with key 'transformation_rules' containing all sub-sections
    (technical_to_corporate, error_messages, status_descriptions,
    feature_descriptions, communication_templates), identical to loading
    the original single-file professional_glossary.yaml.
    """
    rules: dict[str, Any] = {}
    for fragment in sorted(_DIR.glob("_*.yaml")):
        data = yaml.safe_load(fragment.read_text(encoding="utf-8"))
        rules.update(data.get("transformation_rules", {}))
    return {"transformation_rules": rules}
