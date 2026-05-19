"""DNA Templates — Modular YAML loaders.

All YAML files in this directory are split for maintainability (<=400 lines each).
Use these loader functions to get the assembled data as if it were a single file.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


_DNA_DIR = Path(__file__).parent


def load_logic_modules() -> dict[str, Any]:
    """Load and merge all logic module YAML fragments.

    Returns a dict with key 'modules' containing the full list of module definitions,
    identical to loading the original single-file logic_modules.yaml.
    """
    modules: list[dict[str, Any]] = []
    for fragment in sorted((_DNA_DIR).glob("_*.yaml")):
        data = yaml.safe_load(fragment.read_text(encoding="utf-8"))
        modules.extend(data.get("modules", []))
    return {"modules": modules}
